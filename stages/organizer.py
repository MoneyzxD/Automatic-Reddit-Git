"""
organizer.py
============
Organiza os arquivos gerados por idioma, data e história.
Registra estado no banco SQLite.
Enfileira vídeo para upload automático após exportação.

Formato de nome de arquivo:
    {titulo_traduzido_slug}_{data}_{lang}.mp4

Exemplo:
    recusei_dividir_heranca_irma_20240409_pt.mp4
"""
from __future__ import annotations

import re
import shutil
import logging
import json
import os
import tempfile
import unicodedata
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SUBREDDIT_PREFIXES = {
    "aita", "aitah", "tifu", "wibta", "yta", "nta",
    "relationships", "relationship", "askreddit", "mc",
    "maliciouscompliance", "raisedbynarcissists", "rbn",
    "entitledparents", "nosleep", "prorevenge",
}

STOP_WORDS = {
    "eu", "meu", "minha", "meus", "minhas", "que", "para", "com",
    "uma", "mim", "por", "nao", "mas", "ela", "ele", "nos", "foi",
    "ser", "ter", "isso", "esse", "essa", "seu", "sua", "como",
    "quando", "mais", "depois", "antes", "sobre", "entre",
    "i", "my", "me", "a", "an", "the", "and", "or", "but",
    "in", "on", "at", "to", "for", "of", "with", "by", "from",
    "is", "was", "are", "were", "be", "been", "have", "has",
    "do", "did", "not", "so", "if", "as", "up", "it", "its",
    "your", "his", "her", "our", "their", "we", "you", "he",
    "she", "they", "this", "that", "would", "should", "could",
    "yo", "mi", "el", "la", "los", "las", "un",
    "para", "con", "por", "pero", "como", "fue", "era",
}


class FileOrganizer:
    def __init__(self, config: dict, db=None):
        self.config   = config
        self.db       = db
        self.base_dir = Path(config.get("base_dir", "."))

    @staticmethod
    def slugify(text: str, max_words: int = 5) -> str:
        """
        Gera slug limpo para nome de arquivo a partir do título traduzido.
        Remove prefixos de subreddit, stop words e acentos.
        Máximo de 5 palavras significativas.
        """
        text = text.lower()
        text = unicodedata.normalize("NFD", text)
        text = "".join(c for c in text if unicodedata.category(c) != "Mn")
        text = re.sub(r"[^\w\s]", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        words = text.split()

        if words and words[0] in SUBREDDIT_PREFIXES:
            words = words[1:]

        meaningful = [w for w in words if w not in STOP_WORDS and len(w) > 2]

        if not meaningful:
            meaningful = [w for w in words if len(w) > 2]

        if not meaningful:
            return "historia"

        return "_".join(meaningful[:max_words])[:50].rstrip("_")

    def build_filename(self, title: str, language: str, date_str: str,
                       part: int, total: int, extension: str) -> str:
        """
        Monta nome: {slug}_{data}_{lang}[_pt{N}of{M}].{ext}
        Exemplo: recusei_dividir_heranca_irma_20240409_pt.mp4
        """
        slug       = self.slugify(title)
        part_label = f"_pt{part}of{total}" if total > 1 else ""
        return f"{slug}_{date_str}_{language}{part_label}.{extension}"

    def organize_output(self, story_id: str, language: str, part: int,
                        total: int, video_path: Path, thumbnail_path: Path,
                        metadata_path: Path, story_title: str = "") -> dict:
        """
        Copia arquivos finais para exports/ com nomes descritivos e traduzidos.
        Enfileira vídeo para upload automático após exportação.
        """
        date_str   = datetime.now().strftime("%Y%m%d")
        export_dir = self.base_dir / "data" / "exports" / language
        export_dir.mkdir(parents=True, exist_ok=True)

        title = story_title or story_id
        paths = {}

        for src, ext in [
            (video_path,     "mp4"),
            (thumbnail_path, "jpg"),
            (metadata_path,  "json"),
        ]:
            if not src:
                continue
            src = Path(src)
            if not src.exists():
                logger.warning("Arquivo não encontrado: %s", src)
                continue

            dest_name = self.build_filename(title, language, date_str, part, total, ext)
            dest      = export_dir / dest_name
            shutil.copy2(src, dest)
            paths[ext] = str(dest)
            logger.info("Exportado: %s", dest_name)

        # ── ENFILEIRAR PARA UPLOAD AUTOMÁTICO ────────────────────────────────
        # Carrega metadata do JSON exportado para passar para a fila
        self._enqueue_for_upload(
            language=language,
            video_path=paths.get("mp4"),
            thumbnail_path=paths.get("jpg"),
            metadata_path=paths.get("json"),
            title=title,
            story_id=story_id,
            part=part,
            total=total,
        )

        if self.db:
            self.db.update_status(story_id, language, part, "exported", total_parts=total)

        return paths

    def organize_batch(self, outputs: list[dict], *, generation_key: str) -> list[dict]:
        """Copia um conjunto completo e só conclui DB após a fila durável."""
        from scheduler.queue import enqueue_many, QueueStateError
        from utils.pipeline_recovery import file_sha256, json_sha256
        if not outputs or not re.fullmatch(r"[a-f0-9]{64}", generation_key):
            raise QueueStateError("Exportação de batch inválida")
        language, story_id, count = outputs[0]["language"], outputs[0]["story_id"], len(outputs)
        if language not in {"pt", "en", "es"} or not re.fullmatch(r"[A-Za-z0-9_-]+", story_id):
            raise QueueStateError("Identidade do batch inválida")
        metadata, fingerprint = [], []
        for part, output in enumerate(outputs, 1):
            if (output["language"] != language or output["story_id"] != story_id
                    or output["part"] != part or output["total"] != count):
                raise QueueStateError("Exportação do idioma incompleta")
            hashes = {}
            for field in ("video_path", "thumbnail_path", "metadata_path"):
                path = output.get(field)
                if not path and field == "thumbnail_path":
                    continue
                if not path or not Path(path).is_file():
                    raise QueueStateError("Mídia ou metadados de exportação ausentes")
                hashes[field] = file_sha256(Path(path))
            metadata.append(json.loads(Path(output["metadata_path"]).read_text(encoding="utf-8")))
            fingerprint.append(hashes)
        # Conteúdo distingue tentativas sem sobrescrever mídia já enfileirada.
        content_id = json_sha256(fingerprint)[:12]
        directory = self.base_dir / "data/exports" / language / f"{story_id}_{generation_key[:12]}_{content_id}"
        directory.mkdir(parents=True, exist_ok=True)
        paths, items = [], []
        date_str = datetime.now().strftime("%Y%m%d")
        for output, meta in zip(outputs, metadata):
            exported = {}
            for field, ext in (("video_path", "mp4"), ("thumbnail_path", "jpg"), ("metadata_path", "json")):
                if not output.get(field):
                    continue
                destination = directory / self.build_filename(output["story_title"], language, date_str,
                                                                 output["part"], count, ext)
                temporary = None
                try:
                    with tempfile.NamedTemporaryFile(dir=directory, delete=False) as handle:
                        temporary = Path(handle.name)
                    shutil.copy2(output[field], temporary)
                    os.replace(temporary, destination)
                finally:
                    if temporary is not None:
                        temporary.unlink(missing_ok=True)
                exported[ext] = str(destination)
            paths.append(exported)
            items.append(dict(video_path=exported["mp4"], thumbnail_path=exported.get("jpg"), metadata=meta,
                              title=output["story_title"], story_id=story_id, part=output["part"], total=count))
        enqueue_many(language, items, generation_key=generation_key)
        if self.db:
            for output in outputs:
                self.db.update_status(story_id, language, output["part"], "exported", total_parts=count)
        return paths

    def _enqueue_for_upload(
        self,
        language: str,
        video_path: str | None,
        thumbnail_path: str | None,
        metadata_path: str | None,
        title: str,
        story_id: str = "",
        part: int = 1,
        total: int = 1,
    ) -> None:
        """
        Enfileira vídeo exportado para upload automático.
        Falha da fila interrompe a exportação; não pode parecer sucesso.
        """
        if not video_path:
            from scheduler.queue import QueueStateError
            raise QueueStateError("Vídeo ausente para enfileiramento")

        try:
            # Carrega metadata do JSON para passar completo para a fila
            metadata = {}
            if metadata_path and Path(metadata_path).exists():
                import json
                with open(metadata_path, encoding="utf-8") as f:
                    metadata = json.load(f)

            # Importa aqui para evitar import circular no topo
            from scheduler.queue import enqueue
            item_id = enqueue(
                language=language,
                video_path=Path(video_path),
                thumbnail_path=Path(thumbnail_path) if thumbnail_path else None,
                metadata=metadata,
                title=title,
                story_id=story_id,
                part=part,
                total=total,
            )
            logger.info("Enfileirado para upload: %s (%s)", item_id, language)

        except Exception:
            raise
