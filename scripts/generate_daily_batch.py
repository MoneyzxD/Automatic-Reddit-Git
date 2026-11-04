#!/usr/bin/env python3
"""Preenche o lote diario ate a meta exata de videos por idioma."""
from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).parent.parent
if str(BASE_DIR) not in sys.path:
    # Ao executar "python scripts/...", o Python inclui apenas scripts/ no
    # caminho de imports. O runner precisa da raiz para encontrar main.py.
    sys.path.insert(0, str(BASE_DIR))


class BatchUnavailable(RuntimeError):
    """Dependência indisponível não é escondida; outros idiomas podem concluir."""


def _carregar_publicacao() -> dict:
    config_path = BASE_DIR / "config" / "publishing.yaml"
    with open(config_path, encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo) or {}


def _carregar_plano() -> dict:
    return _carregar_publicacao().get("daily_video_plan", {}) or {}


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


def _contar_lote_do_dia(idiomas: list[str], *, reserve_days=None, daily_target=None) -> dict[str, int]:
    import pytz
    from scheduler.queue import count_scheduled_by_local_date, get_pending

    from scheduler.scheduling import daily_reserve_days
    publicacao = _carregar_publicacao()
    canais = publicacao.get("channels", {}) or {}
    dias = daily_reserve_days(publicacao) if reserve_days is None else reserve_days
    meta = _meta_diaria()[0] if daily_target is None else daily_target
    contagens = {}
    for idioma in idiomas:
        canal = canais.get(idioma) or canais.get("pt-br" if idioma == "pt" else idioma, {})
        timezone_name = canal.get("timezone", "UTC")
        try:
            channel_tz = pytz.timezone(timezone_name)
        except Exception:
            channel_tz = pytz.UTC
        hoje = datetime.now(timezone.utc).astimezone(channel_tz).date()
        agendados = count_scheduled_by_local_date(idioma, timezone_name)
        contagens[idioma] = sum(min(meta, agendados.get((hoje + timedelta(days=offset)).isoformat(), 0))
                               for offset in range(dias + 1)) + len(get_pending(idioma))
    return contagens


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
    if len(idiomas) == 1 and not dry_run and not test_story:
        comando.append("--isolar-idioma")
    ambiente = os.environ.copy()
    if len(idiomas) == 1:
        ambiente["PIPELINE_GROQ_WORKLOAD_LANGUAGE"] = "pt" if idiomas[0] == "pt-br" else idiomas[0]
    else:
        ambiente.pop("PIPELINE_GROQ_WORKLOAD_LANGUAGE", None)
    return subprocess.run(comando, cwd=BASE_DIR, check=False, env=ambiente).returncode


def preencher_lote(
    idiomas: list[str],
    meta: int,
    max_tentativas: int,
    max_excedente: int = 1,
    *, explicit_target: int | None = None,
) -> dict[str, int]:
    logger = logging.getLogger("daily_batch")
    def contar():
        if explicit_target is not None:
            return _contar_lote_do_dia(idiomas, reserve_days=0, daily_target=explicit_target)
        return _contar_lote_do_dia(idiomas)
    contagens = contar()
    tentativas = dict.fromkeys(idiomas, 0)
    indisponiveis, esgotados = set(), set()

    while True:
        elegiveis = [idioma for idioma in idiomas if contagens[idioma] < meta
                     and idioma not in indisponiveis | esgotados]
        if not elegiveis:
            break
        # Em empate, dá vez a quem tentou menos; uma recusa PT não retém EN/ES.
        idioma = max(elegiveis, key=lambda lang: (meta - contagens[lang], -tentativas[lang]))
        if tentativas[idioma] >= max_tentativas:
            esgotados.add(idioma)
            continue
        limite_historia = min(3, meta - contagens[idioma] + max_excedente)
        tentativas[idioma] += 1
        logger.info(
            "Historia %d/%d: idioma=%s, ate %d parte(s)",
            tentativas[idioma],
            max_tentativas,
            idioma,
            limite_historia,
        )
        # Um único gravador por vez, com orçamento/tentativas por idioma.
        # A mesma fonte/perfil e os checkpoints aprovados seguem reutilizáveis.
        codigo = _executar_historia([idioma], limite_historia)
        if codigo == 2:
            raise BatchUnavailable("Estado obrigatório indisponível (codigo 2); lote interrompido")
        if codigo == 4:
            indisponiveis.add(idioma)
            logger.error("IA indisponível em %s; sem nova história neste idioma; continuando os demais", idioma)
        elif codigo != 0:
            raise RuntimeError(f"main.py falhou com codigo {codigo}")

        novas_contagens = contar()
        if any(
            novas_contagens[idioma] > meta + max_excedente
            for idioma in idiomas
        ):
            raise RuntimeError(f"Lote ultrapassou o excedente permitido: {novas_contagens}")
        if novas_contagens == contagens:
            logger.warning("Historia nao coube nas vagas restantes; tentando outra")
        contagens = novas_contagens

    if indisponiveis:
        raise BatchUnavailable(f"IA indisponível em {','.join(sorted(indisponiveis))}; lote preservado: {contagens}")
    if esgotados:
        raise RuntimeError(f"Nao foi possivel completar o lote em {max_tentativas} historias por idioma: {contagens}")
    logger.info(
        "Lote completo: %s (ate %d excedente para o dia seguinte)",
        contagens,
        max_excedente,
    )
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
        from scheduler.scheduling import daily_reserve_days
        # Validação explícita --target não constrói reserva de produção.
        if args.target is None:
            meta *= 1 + daily_reserve_days(_carregar_publicacao())
            max_tentativas = max(max_tentativas, meta + 3)
        max_excedente = int(_carregar_plano().get("max_carryover_parts_next_day", 1))
        preencher_lote(idiomas, meta, max_tentativas, max_excedente, explicit_target=args.target)
    except BatchUnavailable as erro:
        logging.getLogger("daily_batch").error("Lote indisponível: %s", erro)
        return 2
    except (OSError, ValueError, RuntimeError) as erro:
        logging.getLogger("daily_batch").error("Lote diario falhou: %s", erro)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
