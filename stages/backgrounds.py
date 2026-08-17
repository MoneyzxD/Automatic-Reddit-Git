"""
stages/backgrounds.py
=====================
Fornece o video de fundo para o render, abstraindo DE ONDE ele vem.

Motivo de existir:
    A biblioteca de backgrounds tem ~800MB (47 arquivos, media 17MB). Numa
    VM isso fica no disco e e so sortear um arquivo. Num runner efemero do
    GitHub Actions nao da para versionar isso no repositorio — cada
    execucao clonaria 800MB para usar 17MB.

    Entao o stage de video NAO decide mais de onde vem o arquivo: ele pede
    um background ao provider e recebe um caminho local, ponto. Trocar de
    ambiente (Oracle <-> runner) e trocar variavel de ambiente, sem tocar
    em video.py.

Providers:
    LocalBackgroundProvider  — sorteia da pasta local (comportamento atual)
    RemoteBackgroundProvider — sorteia do manifesto e baixa so o escolhido

O manifesto (config/backgrounds_manifest.json) e apenas a lista de nomes de
arquivo — poucos KB, versionado no repositorio. Os arquivos em si vivem
fora (ex: assets de release do GitHub), acessados por BACKGROUND_BASE_URL.
Gere/atualize o manifesto com:  python -m stages.backgrounds --gerar-manifesto
"""
from __future__ import annotations

import json
import logging
import random
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}

MANIFEST_PATH = Path(__file__).parent.parent / "config" / "backgrounds_manifest.json"


# ── PROVIDERS ─────────────────────────────────────────────────────────────────

class LocalBackgroundProvider:
    """Sorteia um video da pasta local. Comportamento historico do pipeline."""

    def __init__(self, bg_dir: Path):
        self.bg_dir = Path(bg_dir)

    def get(self) -> Path | None:
        if not self.bg_dir.exists():
            logger.warning("Pasta de backgrounds nao encontrada: %s", self.bg_dir)
            return None
        videos = [f for f in self.bg_dir.iterdir() if f.suffix.lower() in _VIDEO_EXTS]
        if not videos:
            logger.warning("Nenhum video encontrado em: %s", self.bg_dir)
            return None
        chosen = random.choice(videos)
        logger.info(
            "Background selecionado (local): %s (%d disponiveis)",
            chosen.name, len(videos),
        )
        return chosen


class RemoteBackgroundProvider:
    """
    Sorteia um nome do manifesto e baixa APENAS esse arquivo.

    Cache: se o mesmo arquivo ja foi baixado nesta execucao (job que gera
    varios videos), reaproveita em vez de baixar de novo.

    Fallback: se o download falhar, cai para a pasta local se ela existir —
    isso mantem a maquina de desenvolvimento e a Oracle funcionando mesmo
    com BACKGROUND_BASE_URL definida por engano.
    """

    def __init__(self, base_url: str, cache_dir: Path,
                 manifest_path: Path = MANIFEST_PATH,
                 local_fallback_dir: Path | None = None):
        self.base_url           = base_url.rstrip("/")
        self.cache_dir          = Path(cache_dir)
        self.manifest_path      = Path(manifest_path)
        self.local_fallback_dir = local_fallback_dir

    def _load_manifest(self) -> list[str]:
        if not self.manifest_path.exists():
            logger.error(
                "Manifesto de backgrounds nao encontrado: %s — "
                "gere com: python -m stages.backgrounds --gerar-manifesto",
                self.manifest_path,
            )
            return []
        try:
            with open(self.manifest_path, encoding="utf-8") as f:
                data = json.load(f)
            return [str(n) for n in data.get("files", []) if str(n).strip()]
        except Exception as e:
            logger.error("Falha ao ler manifesto de backgrounds: %s", e)
            return []

    def _download(self, filename: str) -> Path | None:
        destino = self.cache_dir / filename
        if destino.exists() and destino.stat().st_size > 0:
            logger.info("Background reaproveitado do cache: %s", filename)
            return destino

        url = f"{self.base_url}/{quote(filename)}"
        try:
            import requests
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.info("Baixando background: %s", filename)
            with requests.get(url, stream=True, timeout=180) as resp:
                resp.raise_for_status()
                parcial = destino.with_suffix(destino.suffix + ".part")
                with open(parcial, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=1024 * 512):
                        if chunk:
                            f.write(chunk)
                parcial.replace(destino)
            mb = destino.stat().st_size / (1024 * 1024)
            logger.info("Background baixado: %s (%.1fMB)", filename, mb)
            return destino
        except Exception as e:
            logger.error("Falha ao baixar background %s: %s", filename, e)
            return None

    def get(self) -> Path | None:
        nomes = self._load_manifest()
        if nomes:
            # Tenta ate 3 nomes distintos antes de desistir — um asset
            # removido do release nao pode derrubar o render inteiro.
            for tentativa, escolhido in enumerate(random.sample(nomes, min(3, len(nomes))), 1):
                caminho = self._download(escolhido)
                if caminho:
                    logger.info(
                        "Background selecionado (remoto): %s (%d no manifesto)",
                        escolhido, len(nomes),
                    )
                    return caminho
                logger.warning("Tentativa %d de background falhou — sorteando outro", tentativa)

        if self.local_fallback_dir and Path(self.local_fallback_dir).exists():
            logger.warning("Backgrounds remotos indisponiveis — usando pasta local")
            return LocalBackgroundProvider(self.local_fallback_dir).get()

        logger.error("Nenhum background disponivel (remoto nem local)")
        return None


# ── FABRICA ───────────────────────────────────────────────────────────────────

def build_provider(base_dir: Path, bg_dir: Path | None = None):
    """
    Constroi o provider certo a partir do ambiente (utils/environment.py).
    Sem variavel de ambiente definida, devolve o provider local — ou seja,
    o comportamento identico ao de hoje.
    """
    from utils import environment as env

    pasta = Path(bg_dir) if bg_dir else env.background_dir(base_dir)

    if env.background_source() == "remote":
        return RemoteBackgroundProvider(
            base_url=env.background_base_url(),
            cache_dir=env.background_cache_dir(),
            local_fallback_dir=pasta,
        )
    return LocalBackgroundProvider(pasta)


# ── GERACAO DO MANIFESTO ──────────────────────────────────────────────────────

def gerar_manifesto(bg_dir: Path, manifest_path: Path = MANIFEST_PATH) -> int:
    """
    Varre a pasta local e grava o manifesto com os nomes dos arquivos.
    Rode isto sempre que adicionar/remover backgrounds da biblioteca.
    Retorna a quantidade de arquivos listados.
    """
    bg_dir = Path(bg_dir)
    videos = sorted(
        f.name for f in bg_dir.iterdir() if f.suffix.lower() in _VIDEO_EXTS
    ) if bg_dir.exists() else []

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"files": videos}, f, ensure_ascii=False, indent=2)

    print(f"Manifesto gravado: {manifest_path} ({len(videos)} arquivos)")
    return len(videos)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Utilitario de backgrounds")
    parser.add_argument("--gerar-manifesto", action="store_true")
    parser.add_argument("--dir", default=None, help="pasta de backgrounds")
    args = parser.parse_args()

    base = Path(__file__).parent.parent
    pasta = Path(args.dir) if args.dir else base / "background" / "Shorts"

    if args.gerar_manifesto:
        gerar_manifesto(pasta)
    else:
        parser.print_help()
