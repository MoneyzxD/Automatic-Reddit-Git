#!/usr/bin/env python3
"""
publish.py
==========
Publica os videos que ja estao na fila. Roda igual em VM e em runner efemero.

Por que e um processo separado de main.py:
    main.py GERA o video e enfileira. Este script PUBLICA. A separacao
    permite:
      - rodar os dois no mesmo job (runner efemero, onde o arquivo de video
        so existe durante aquele job)
      - rodar separados numa VM (comportamento historico, com o scheduler
        chamando o upload em outro momento)
    Nenhum dos dois modos exige alteracao de codigo — so muda quem chama.

Ordem deliberada por item:
    1. Kit do TikTok pelo Telegram (ENQUANTO o arquivo local existe)
    2. Upload para o YouTube com publishAt (o YouTube segura e publica sozinho)
    3. Atualizacao do status na fila

    O TikTok vem primeiro de proposito: o upload do YouTube pode disparar a
    remocao do arquivo local (delete_after_upload), e sem o arquivo nao ha
    kit para enviar. Em runner o arquivo morre junto com o job de qualquer
    forma — se o kit nao sair aqui, nao sai nunca.

Uso:
    python publish.py --lang pt
    python publish.py --lang pt en es --max 5
    python publish.py --lang pt --dry-run     # nao sobe nada, so mostra o plano
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

BASE_DIR = Path(__file__).parent


def _carregar_publishing() -> dict:
    import yaml
    caminho = BASE_DIR / "config" / "publishing.yaml"
    if not caminho.exists():
        logging.getLogger("publish").error("publishing.yaml nao encontrado")
        return {}
    with open(caminho, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _enviar_kit_tiktok(language: str, item: dict, pub_cfg: dict) -> bool:
    """
    Envia o kit de postagem manual do TikTok pelo Telegram.
    O video enviado fica guardado no proprio chat — e isso que torna o
    TikTok viavel em runner efemero, onde o arquivo local nao sobrevive.
    """
    tiktok_cfg = pub_cfg.get("tiktok", {})
    if not tiktok_cfg.get("enabled", False):
        logging.getLogger("publish").debug("TikTok desabilitado — kit nao enviado")
        return False
    if tiktok_cfg.get("api_enabled", False):
        logging.getLogger("publish").debug("API TikTok ativa — kit manual dispensado")
        return False

    from scheduler.notifier import TikTokNotifier
    from scheduler.queue import update_status

    notifier = TikTokNotifier(config=pub_cfg)
    ok = notifier.send(
        language=language,
        video_path=item["video_path"],
        metadata=item.get("metadata", {}),
        video_id=item["id"],
    )
    if ok:
        # 'uploading' tira da fila de pendentes; o status final vem do
        # operador respondendo /ok ou /fail no Telegram.
        update_status(language, item["id"], "tiktok", "uploading")
    return ok


def publicar_idioma(language: str, pub_cfg: dict, maximo: int,
                     dry_run: bool = False) -> dict:
    """Publica ate `maximo` itens pendentes do idioma. Retorna resumo."""
    logger = logging.getLogger("publish")
    from scheduler.queue import get_pending, update_status

    resumo = {"idioma": language, "enviados": 0, "falhas": 0, "kits_tiktok": 0,
              "agendamentos": []}

    canais = pub_cfg.get("channels", {})
    canal  = canais.get(language) or canais.get("pt-br" if language == "pt" else language)
    if not canal:
        logger.warning("Sem configuracao de canal para '%s' — pulando", language)
        return resumo
    if not canal.get("enabled", True):
        logger.info("Canal %s desabilitado — pulando", language)
        return resumo

    pendentes = get_pending(language)
    if not pendentes:
        logger.info("Fila vazia: %s", language)
        return resumo

    # Limites do growth_plan (rampa por idade da conta, anti-block). Reusa a
    # funcao do runner de proposito: duplicar essa regra criaria uma segunda
    # fonte de verdade para limites que existem por seguranca da conta.
    from scheduler.runner import _get_limits_for_channel
    limites = _get_limits_for_channel(canal, pub_cfg)
    teto_diario = int(limites.get("max_uploads_per_day", 1))
    intervalo   = int(limites.get("min_interval_minutes", 360))

    ja_hoje = 0
    try:
        from scheduler.queue import count_uploads_today
        ja_hoje = count_uploads_today(language)
    except Exception as e:
        logger.debug("Nao foi possivel contar uploads de hoje (%s): %s", language, e)

    restante = max(0, teto_diario - ja_hoje)
    limite_efetivo = min(maximo, restante)

    logger.info(
        "%d pendente(s) em %s | growth_plan: %d/dia (ja publicados hoje: %d, "
        "intervalo %dmin) -> processando %d",
        len(pendentes), language, teto_diario, ja_hoje, intervalo, limite_efetivo,
    )

    if limite_efetivo <= 0:
        logger.info(
            "Teto diario do growth_plan ja atingido em %s (%d/%d) — nada a publicar",
            language, ja_hoje, teto_diario,
        )
        return resumo

    maximo = limite_efetivo

    # Calcula TODOS os horarios de uma vez: o calculo sequencial garante
    # ordem crescente entre eles (item por item, ancorado em "agora", os
    # excedentes que caem no dia seguinte saem fora de ordem).
    from scheduler.scheduling import next_publish_slots, to_youtube_timestamp

    lote = pendentes[:maximo]
    horarios = next_publish_slots(language, canal, len(lote),
                                   intervalo_minutos=intervalo)

    for indice, item in enumerate(lote):
        item_id = item["id"]
        quando  = to_youtube_timestamp(horarios[indice])
        resumo["agendamentos"].append((item_id, quando))

        if dry_run:
            logger.info("[dry-run] %s -> publicaria em %s", item_id, quando)
            continue

        # 1. Kit do TikTok primeiro — depende do arquivo local existir
        try:
            if _enviar_kit_tiktok(language, item, pub_cfg):
                resumo["kits_tiktok"] += 1
                logger.info("Kit TikTok enviado: %s", item_id)
        except Exception as e:
            logger.warning("Falha ao enviar kit TikTok (%s): %s", item_id, e)

        # 2. Upload para o YouTube com publicacao agendada
        try:
            from scheduler.uploader import Uploader
            uploader = Uploader(language, canal)
            resultado = uploader.upload_item(item, publish_at=quando)
            yt = resultado.get("youtube", {})
            if yt.get("status") == "uploaded":
                resumo["enviados"] += 1
                logger.info("Publicado: %s -> %s (ao vivo em %s)",
                            item_id, yt.get("url"), quando)
            else:
                resumo["falhas"] += 1
                logger.error("Falha no upload de %s: %s", item_id, yt.get("error"))
        except Exception as e:
            resumo["falhas"] += 1
            logger.error("Erro inesperado publicando %s: %s", item_id, e)
            try:
                update_status(language, item_id, "youtube", "failed")
            except Exception:
                pass

    return resumo


def main() -> int:
    parser = argparse.ArgumentParser(description="Publica videos ja enfileirados")
    parser.add_argument("--lang", nargs="+", default=["pt"])
    parser.add_argument("--max", type=int, default=10,
                        help="maximo de videos por idioma nesta execucao")
    parser.add_argument("--dry-run", action="store_true",
                        help="mostra o que seria publicado, sem enviar nada")
    args = parser.parse_args()

    from main import setup_logging
    setup_logging(BASE_DIR / "data" / "logs")
    logger = logging.getLogger("publish")

    from utils import environment as env
    logger.info("Ambiente: %s", env.describe(BASE_DIR))

    pub_cfg = _carregar_publishing()
    if not pub_cfg:
        logger.error("publishing.yaml vazio — nada a fazer")
        return 1

    if not pub_cfg.get("global", {}).get("enabled", False) and not args.dry_run:
        logger.warning(
            "Publicacao desabilitada (global.enabled=false em publishing.yaml). "
            "Nada sera enviado. Use --dry-run para simular ou ative quando pronto."
        )
        return 0

    # Normaliza pt-br -> pt, mesma regra do main.py (ponto de entrada unico)
    idiomas = ["pt" if l == "pt-br" else l for l in args.lang]

    inicio = datetime.now()
    resumos = [publicar_idioma(l, pub_cfg, args.max, args.dry_run) for l in idiomas]

    total_env = sum(r["enviados"] for r in resumos)
    total_fal = sum(r["falhas"] for r in resumos)
    total_kit = sum(r["kits_tiktok"] for r in resumos)
    duracao   = (datetime.now() - inicio).total_seconds() / 60

    logger.info("=" * 60)
    logger.info("PUBLICACAO CONCLUIDA: %d enviado(s), %d falha(s), %d kit(s) TikTok "
                "em %.1f min", total_env, total_fal, total_kit, duracao)
    for r in resumos:
        for item_id, quando in r["agendamentos"]:
            logger.info("  %s (%s) -> %s", item_id, r["idioma"], quando)

    # Resumo no Telegram — mesmo canal dos outros avisos administrativos
    if not args.dry_run and (total_env or total_fal):
        try:
            from scheduler.notifier import send_admin_alert
            icone = "✅" if total_fal == 0 else ("⚠️" if total_env else "❌")
            linhas = [
                f"{icone} Publicacao — {total_env} enviado(s), {total_fal} falha(s)",
                f"Kits TikTok: {total_kit}",
                f"Duracao: {duracao:.1f} min",
            ]
            for r in resumos:
                for item_id, quando in r["agendamentos"]:
                    linhas.append(f"• {item_id[:45]} ({r['idioma']}) → {quando}")
            send_admin_alert("\n".join(linhas), pub_cfg)
        except Exception as e:
            logger.warning("Falha ao enviar resumo no Telegram: %s", e)

    return 0 if total_fal == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
