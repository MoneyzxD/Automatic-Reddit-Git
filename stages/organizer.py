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

        if self.db:
            self.db.update_status(
                story_id, language, part, "exported",
                export_dir=str(export_dir),
            )

        # ── ENFILEIRAR PARA UPLOAD AUTOMÁTICO ────────────────────────────────
        # Carrega metadata do JSON exportado para passar para a fila
        self._enqueue_for_upload(
            language=language,
            video_path=paths.get("mp4"),
            thumbnail_path=paths.get("jpg"),
            metadata_path=paths.get("json"),
            title=title,
        )

        return paths

    def _enqueue_for_upload(
        self,
        language: str,
        video_path: str | None,
        thumbnail_path: str | None,
        metadata_path: str | None,
        title: str,
    ) -> None:
        """
        Enfileira vídeo exportado para upload automático.
        Falha silenciosa — problema na fila não deve quebrar o pipeline.
        """
        if not video_path:
            logger.warning("Sem video_path para enfileirar (%s)", language)
            return

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
            )
            logger.info("Enfileirado para upload: %s (%s)", item_id, language)

        except ImportError:
            # scheduler ainda não instalado — ignora silenciosamente
            logger.debug("scheduler/queue.py não encontrado — enqueue ignorado")
        except Exception as e:
            # Nunca quebra o pipeline por falha na fila
            logger.warning("Falha ao enfileirar %s (%s): %s", title, language, e)