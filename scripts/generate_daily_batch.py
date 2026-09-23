#!/usr/bin/env python3
"""Preenche o lote diario ate a meta exata de videos por idioma."""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent.parent


def _carregar_plano() -> dict:
    config_path = BASE_DIR / "config" / "publishing.yaml"
    with open(config_path, encoding="utf-8") as arquivo:
        config = yaml.safe_load(arquivo) or {}
    return config.get("daily_video_plan", {}) or {}


def _meta_diaria(valor_cli: int | None = None) -> tuple[int, int]:
    plano = _carregar_plano()
    maximo = int(plano.get("maximum_target_per_language", 10))
    bruto = valor_cli if valor_cli is not None else os.environ.get(
        "DAILY_VIDEO_TARGET",
        plano.get("target_per_language", 3),
    )
    meta = int(bruto)
    if not 1 <= meta <= maximo:
        raise ValueError(f"Meta diaria deve ficar entre 1 e {maximo}; recebido: {meta}")
    minimo_tentativas = int(plano.get("max_story_attempts", 6))
    return meta, max(minimo_tentativas, meta + 3)


def _contar_lote_do_dia(idiomas: list[str]) -> dict[str, int]:
    from scheduler.queue import count_uploads_today, get_pending

    return {
        idioma: count_uploads_today(idioma) + len(get_pending(idioma))
        for idioma in idiomas
    }


def _executar_historia(
    idiomas: list[str],
    max_parts: int,
    dry_run: bool = False,
    test_story: bool = False,
) -> int:
    comando = [
        sys.executable,
        str(BASE_DIR / "main.py"),
        "--lang",
        *idiomas,
        "--max-parts",
        str(max_parts),
    ]
    if dry_run:
        comando.append("--dry-run")
    if test_story:
        comando.append("--test-story")
    return subprocess.run(comando, cwd=BASE_DIR, check=False).returncode


def preencher_lote(
    idiomas: list[str],
    meta: int,
    max_tentativas: int,
) -> dict[str, int]:
    logger = logging.getLogger("daily_batch")
    contagens = _contar_lote_do_dia(idiomas)
    tentativas = 0

    while any(contagens[idioma] < meta for idioma in idiomas):
        if tentativas >= max_tentativas:
            faltando = ", ".join(
                f"{idioma}={contagens[idioma]}/{meta}" for idioma in idiomas
            )
            raise RuntimeError(
                f"Nao foi possivel completar o lote em {max_tentativas} historias: {faltando}"
            )

        restantes = {idioma: meta - contagens[idioma] for idioma in idiomas}
        maior_falta = max(restantes.values())
        grupo = [idioma for idioma, falta in restantes.items() if falta == maior_falta]
        limite_historia = min(3, maior_falta)

        tentativas += 1
        logger.info(
            "Historia %d/%d: idiomas=%s, ate %d parte(s)",
            tentativas,
            max_tentativas,
            ",".join(grupo),
            limite_historia,
        )
        codigo = _executar_historia(grupo, limite_historia)
        if codigo != 0:
            raise RuntimeError(f"main.py falhou com codigo {codigo}")

        novas_contagens = _contar_lote_do_dia(idiomas)
        if any(novas_contagens[idioma] > meta for idioma in idiomas):
            raise RuntimeError(f"Lote ultrapassou a meta diaria: {novas_contagens}")
        if novas_contagens == contagens:
            logger.warning("Historia nao coube nas vagas restantes; tentando outra")
        contagens = novas_contagens

    logger.info("Lote diario completo: %s", contagens)
    return contagens


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Preenche o lote diario de videos")
    parser.add_argument("--lang", nargs="+", default=["pt"])
    parser.add_argument("--target", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--test-story", action="store_true")
    args = parser.parse_args(argv)

    from main import setup_logging

    setup_logging(BASE_DIR / "data" / "logs")
    idiomas = ["pt" if idioma == "pt-br" else idioma for idioma in args.lang]

    # Dry-run e historia fixa continuam sendo testes de uma unica historia;
    # repetir TEST_STORY criaria copias artificiais e nao valida o lote real.
    if args.dry_run or args.test_story:
        return _executar_historia(
            idiomas,
            max_parts=3,
            dry_run=args.dry_run,
            test_story=args.test_story,
        )

    try:
        meta, max_tentativas = _meta_diaria(args.target)
        preencher_lote(idiomas, meta, max_tentativas)
    except (OSError, ValueError, RuntimeError) as erro:
        logging.getLogger("daily_batch").error("Lote diario falhou: %s", erro)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
