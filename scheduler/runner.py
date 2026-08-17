"""
scheduler/runner.py
===================
Processo continuo que gerencia o pipeline e uploads automaticos.

Jobs principais:
    pipeline_job      — roda main.py no horario configurado (gera videos)
    upload_job        — verifica filas a cada 5 min e dispara uploads YouTube
    tiktok_notify_job — verifica fila TikTok e envia notificacoes Telegram
    reset_job         — reseta contadores diarios na virada do dia

Anti-block implementado:
    - Posting window por dia da semana e timezone por idioma
    - Growth plan automatico baseado em account_created
    - Limite diario de uploads por idioma
    - Intervalo minimo entre uploads
    - Delay aleatorio antes de cada upload
    - Jitter de volume diario (nem sempre posta o maximo)
    - Pausa ocasional mensal (1 dia sem postagem)
    - Cap diario de notificacoes TikTok por idioma

Uso:
    python -m scheduler.runner
    python scheduler/runner.py
"""
from __future__ import annotations

import logging
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

# Caminhos possiveis para configs
_BASE_PATHS = [
    Path("."),
    Path(__file__).parent.parent,
]

_DAYS_MAP = {
    "mon": 0, "tue": 1, "wed": 2, "thu": 3,
    "fri": 4, "sat": 5, "sun": 6,
}


def _find_base_dir() -> Path:
    for path in _BASE_PATHS:
        if (path / "config" / "publishing.yaml").exists():
            return path
    return Path(".")


def _load_publishing_config() -> dict:
    base = _find_base_dir()
    path = base / "config" / "publishing.yaml"
    if not path.exists():
        logger.error("publishing.yaml nao encontrado em: %s", path)
        return {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error("Erro ao carregar publishing.yaml: %s", e)
        return {}


# ── GROWTH PLAN ───────────────────────────────────────────────────────────────

def _get_current_week(account_created: str) -> int:
    """
    Calcula semana atual baseado na data de criacao da conta.
    Retorna numero da semana (1, 2, 3, 4, 5+).
    """
    try:
        created = datetime.fromisoformat(account_created).replace(tzinfo=timezone.utc)
        now     = datetime.now(timezone.utc)
        days    = (now - created).days
        week    = (days // 7) + 1
        return min(week, 5)  # 5+ agrupado em 5
    except Exception:
        return 5  # Se nao conseguir calcular, usa semana 5 (maduro)


def _get_limits_for_channel(channel_cfg: dict, pub_cfg: dict) -> dict:
    """
    Retorna limites de upload para o canal baseado no growth_plan.
    Se growth_plan desativado, usa os valores diretos do canal.
    """
    growth = pub_cfg.get("growth_plan", {})
    if not growth.get("enabled", True):
        return {
            "max_uploads_per_day":  channel_cfg.get("max_uploads_per_day", 1),
            "min_interval_minutes": channel_cfg.get("min_interval_minutes", 360),
        }

    account_created = channel_cfg.get("account_created", "2026-01-01")
    week            = _get_current_week(account_created)

    if week >= 5:
        limits = growth.get("week_5_plus", {})
    else:
        limits = growth.get(f"week_{week}", {})

    return {
        "max_uploads_per_day":  limits.get("max_uploads_per_day",
                                            channel_cfg.get("max_uploads_per_day", 1)),
        "min_interval_minutes": limits.get("min_interval_minutes",
                                            channel_cfg.get("min_interval_minutes", 360)),
    }


# ── POSTING WINDOW ────────────────────────────────────────────────────────────

def _is_within_posting_window(channel_cfg: dict) -> bool:
    """
    Verifica se o momento atual esta dentro da janela de postagem
    configurada para o idioma (respeita timezone do canal).
    """
    try:
        import pytz
        tz_name   = channel_cfg.get("timezone", "UTC")
        tz        = pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        weekday   = now_local.weekday()  # 0=segunda, 6=domingo

        day_names = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
        day_key   = day_names[weekday]

        windows = channel_cfg.get("posting_windows_by_weekday", {})
        window  = windows.get(day_key, {})

        if not window:
            start_str = "10:00"
            end_str   = "22:00"
        else:
            start_str = window.get("start", "10:00")
            end_str   = window.get("end",   "22:00")

        start_h, start_m = map(int, start_str.split(":"))
        end_h,   end_m   = map(int, end_str.split(":"))

        start_time = now_local.replace(hour=start_h, minute=start_m,
                                       second=0, microsecond=0)
        end_time   = now_local.replace(hour=end_h,   minute=end_m,
                                       second=0, microsecond=0)

        in_window = start_time <= now_local <= end_time
        if not in_window:
            logger.debug(
                "Fora da janela de postagem (%s): %s (janela: %s-%s)",
                tz_name, now_local.strftime("%H:%M"), start_str, end_str,
            )
        return in_window

    except Exception as e:
        logger.debug("Erro ao verificar posting window: %s", e)
        return True  # Em caso de erro, permite upload


def _is_within_tiktok_window(language: str, pub_cfg: dict) -> bool:
    """
    Verifica se o horario atual esta dentro de uma janela TikTok
    configurada em publishing.yaml > tiktok > posting_windows.
    """
    try:
        import pytz

        tiktok_cfg = pub_cfg.get("tiktok", {})
        windows    = tiktok_cfg.get("posting_windows", {}).get(language, [])

        if not windows:
            return True  # Sem restricao configurada

        tz_map = {
            "pt-br": "America/Sao_Paulo",
            "en":    "America/New_York",
            "es":    "America/Mexico_City",
        }
        tz        = pytz.timezone(tz_map.get(language, "UTC"))
        now_local = datetime.now(tz)
        current   = now_local.strftime("%H:%M")

        for window in windows:
            start, end = window.split("-")
            if start <= current <= end:
                return True

        return False

    except Exception as e:
        logger.debug("Erro ao verificar janela TikTok (%s): %s", language, e)
        return True  # Em caso de erro, permite notificacao


def _should_pause_today(language: str) -> bool:
    """
    Pausa ocasional: ~1 dia por mes por idioma sem postagem.
    Usa hash deterministico baseado em idioma + data para consistencia.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    seed  = hash(f"{language}{today}") % 30  # valor 0-29
    if seed == 0:
        logger.info("Pausa ocasional ativa para %s hoje (%s)", language, today)
        return True
    return False


def _should_apply_volume_jitter(max_uploads: int) -> int:
    """
    Jitter de volume: nem sempre posta o maximo diario.
    Retorna o limite real para hoje.
    """
    if max_uploads <= 1:
        return max_uploads
    if random.random() < 0.30:
        return max(1, max_uploads - 1)
    return max_uploads


# ── VERIFICACAO DE CONDICOES ──────────────────────────────────────────────────

def _can_upload(language: str, channel_cfg: dict, pub_cfg: dict) -> tuple[bool, str]:
    """
    Verifica todas as condicoes antes de disparar um upload YouTube.
    Retorna (pode_fazer_upload, motivo_se_nao).
    """
    from scheduler.queue import count_uploads_today, get_last_upload_time

    if not channel_cfg.get("enabled", True):
        return False, "canal desabilitado"

    if not pub_cfg.get("global", {}).get("enabled", False):
        return False, "publicacao global desabilitada (global.enabled=false)"

    if _should_pause_today(language):
        return False, "pausa ocasional do dia"

    if not _is_within_posting_window(channel_cfg):
        return False, "fora da janela de postagem"

    limits        = _get_limits_for_channel(channel_cfg, pub_cfg)
    max_uploads   = _should_apply_volume_jitter(limits["max_uploads_per_day"])
    uploads_today = count_uploads_today(language)
    if uploads_today >= max_uploads:
        return False, f"limite diario atingido ({uploads_today}/{max_uploads})"

    last_upload = get_last_upload_time(language)
    if last_upload:
        min_interval = timedelta(minutes=limits["min_interval_minutes"])
        elapsed      = datetime.now(timezone.utc) - last_upload
        if elapsed < min_interval:
            remaining = (min_interval - elapsed).seconds // 60
            return False, f"intervalo minimo: faltam {remaining}min"

    return True, "ok"


def _can_notify_tiktok(language: str, pub_cfg: dict) -> tuple[bool, str]:
    """
    Verifica todas as condicoes antes de enviar notificacao TikTok.
    Retorna (pode_notificar, motivo_se_nao).
    """
    from scheduler.queue import count_uploads_today

    tiktok_cfg = pub_cfg.get("tiktok", {})

    # TikTok habilitado no config
    if not tiktok_cfg.get("enabled", False):
        return False, "tiktok desabilitado no config"

    # Se API oficial estiver ativa, uploader cuida — notifier nao atua
    if tiktok_cfg.get("api_enabled", False):
        return False, "api tiktok ativa — uploader assume"

    # Telegram configurado
    tg_cfg = pub_cfg.get("telegram", {})
    if not tg_cfg.get("bot_token") and not os.environ.get("TELEGRAM_BOT_TOKEN"):
        return False, "TELEGRAM_BOT_TOKEN nao configurado"

    chat_id = tg_cfg.get("chats", {}).get(language)
    if not chat_id:
        return False, f"chat_id telegram nao configurado para {language}"

    # Janela de horario TikTok
    if not _is_within_tiktok_window(language, pub_cfg):
        return False, "fora da janela de postagem TikTok"

    # Cap diario
    max_per_day   = tg_cfg.get("max_notifications_per_day", 3)
    uploads_today = count_uploads_today(language)
    if uploads_today >= max_per_day:
        return False, f"cap diario TikTok atingido ({uploads_today}/{max_per_day})"

    return True, "ok"


# ── JOBS ──────────────────────────────────────────────────────────────────────

def pipeline_job(pub_cfg: dict) -> None:
    """
    Roda o pipeline de geracao de conteudo para cada idioma.
    Chamado pelo scheduler no horario configurado.
    """
    base_dir  = _find_base_dir()
    main_path = base_dir / "pipeline" / "main.py"

    if not main_path.exists():
        main_path = base_dir / "main.py"

    if not main_path.exists():
        logger.error("main.py nao encontrado em: %s", base_dir)
        return

    pj_cfg    = pub_cfg.get("pipeline_job", {})
    languages = pj_cfg.get("languages", ["pt", "en", "es"])

    logger.info("=" * 60)
    logger.info("PIPELINE JOB — gerando conteudo para: %s", languages)

    for lang in languages:
        try:
            logger.info("Rodando pipeline para: %s", lang.upper())
            result = subprocess.run(
                [sys.executable, str(main_path), "--lang", lang],
                cwd=str(base_dir),
                capture_output=False,
                timeout=3600,
            )
            if result.returncode == 0:
                logger.info("Pipeline concluido: %s", lang.upper())
            else:
                logger.error("Pipeline falhou (%s): codigo %d",
                             lang.upper(), result.returncode)
        except subprocess.TimeoutExpired:
            logger.error("Pipeline timeout (1h): %s", lang.upper())
        except Exception as e:
            logger.error("Erro no pipeline (%s): %s", lang.upper(), e)


def upload_job(pub_cfg: dict) -> None:
    """
    Verifica filas YouTube e dispara uploads quando condicoes OK.
    Chamado a cada queue_check_interval_minutes.
    """
    from scheduler.queue import get_pending, get_failed, increment_attempts
    from scheduler.uploader import Uploader

    channels  = pub_cfg.get("channels", {})
    platforms = pub_cfg.get("global", {}).get("platforms", [])

    if not platforms:
        logger.debug("Nenhuma plataforma configurada")
        return

    for language, channel_cfg in channels.items():
        if not channel_cfg.get("enabled", True):
            continue

        can_upload, reason = _can_upload(language, channel_cfg, pub_cfg)
        if not can_upload:
            logger.debug("Upload bloqueado (%s): %s", language, reason)
            continue

        pending = get_pending(language)
        if not pending:
            logger.debug("Fila YouTube vazia: %s", language)
            continue

        item = pending[0]

        # Delay aleatorio anti-padrao
        random_delay = channel_cfg.get("random_delay_minutes", 30)
        delay        = random.uniform(0, random_delay * 60)
        logger.info(
            "Upload YouTube agendado para %s em %.0fs (delay aleatorio)",
            language, delay,
        )
        time.sleep(delay)

        # Re-verificar condicoes apos delay
        can_upload, reason = _can_upload(language, channel_cfg, pub_cfg)
        if not can_upload:
            logger.debug("Upload cancelado apos delay (%s): %s", language, reason)
            continue

        try:
            uploader = Uploader(language, channel_cfg)
            results  = uploader.upload_item(item)
            logger.info("Resultado upload YouTube %s: %s", language, results)
        except Exception as e:
            logger.error("Erro no uploader YouTube (%s): %s", language, e)
            increment_attempts(language, item["id"])

        # Retry de itens com falha
        retry_attempts = pub_cfg.get("global", {}).get("retry_attempts", 3)
        failed = get_failed(language, max_attempts=retry_attempts)
        for failed_item in failed[:1]:
            logger.info("Retry YouTube: %s (%s)", failed_item["id"], language)
            try:
                uploader = Uploader(language, channel_cfg)
                uploader.upload_item(failed_item)
            except Exception as e:
                logger.error("Retry falhou (%s): %s", language, e)
                increment_attempts(language, failed_item["id"])


def tiktok_notify_job(pub_cfg: dict) -> None:
    """
    Verifica fila TikTok e envia notificacoes Telegram para itens pendentes.
    Chamado a cada queue_check_interval_minutes (mesmo intervalo do YouTube).

    Fluxo:
        1. Verifica condicoes (janela, cap diario, config)
        2. Busca proximo item pendente na fila TikTok
        3. Envia kit de postagem via Telegram
        4. Atualiza status do item para 'notified'
    """
    from scheduler.queue import get_pending, update_status, increment_attempts
    from scheduler.notifier import TikTokNotifier

    tiktok_cfg = pub_cfg.get("tiktok", {})

    # Verifica se TikTok esta habilitado globalmente
    if not tiktok_cfg.get("enabled", False):
        logger.debug("TikTok desabilitado no config — tiktok_notify_job ignorado")
        return

    # Se API oficial estiver ativa, uploader assume — notifier nao atua
    if tiktok_cfg.get("api_enabled", False):
        logger.debug("API TikTok ativa — notifier desativado")
        return

    notifier = TikTokNotifier(config=pub_cfg)

    for language in ["pt", "en", "es"]:
        can_notify, reason = _can_notify_tiktok(language, pub_cfg)
        if not can_notify:
            logger.debug("Notificacao TikTok bloqueada (%s): %s", language, reason)
            continue

        pending = get_pending(language)
        if not pending:
            logger.debug("Fila TikTok vazia: %s", language)
            continue

        item      = pending[0]
        video_id  = item.get("id")
        video_path = item.get("video_path")
        metadata  = item.get("metadata", {})

        if not video_path or not Path(video_path).exists():
            logger.warning(
                "[tiktok_notify] Arquivo nao encontrado para %s (%s): %s",
                video_id, language, video_path
            )
            increment_attempts(language, video_id)
            continue

        logger.info(
            "[tiktok_notify] Enviando notificacao: %s (%s)",
            video_id, language
        )

        success = notifier.send(
            language=language,
            video_path=video_path,
            metadata=metadata,
            video_id=video_id,
        )

        if success:
            # Marca como 'uploading' para sair da fila pending
            # Status final (uploaded/failed) vem via /ok ou /fail do operador
            update_status(language, video_id, "tiktok", "uploading")
            logger.info(
                "[tiktok_notify] Notificacao enviada com sucesso: %s (%s)",
                video_id, language
            )
        else:
            increment_attempts(language, video_id)
            logger.warning(
                "[tiktok_notify] Falha ao enviar notificacao: %s (%s)",
                video_id, language
            )


def reset_daily_counters(pub_cfg: dict) -> None:
    """Reseta contadores diarios de upload. Chamado na virada do dia."""
    from scheduler.queue import reset_daily_counter
    channels = pub_cfg.get("channels", {})
    for language in channels:
        reset_daily_counter(language)
    logger.info("Contadores diarios resetados")


# ── RUNNER PRINCIPAL ──────────────────────────────────────────────────────────

def run() -> None:
    """
    Inicia o scheduler com APScheduler.
    Registra jobs e mantém processo rodando.
    """
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.error(
            "APScheduler nao instalado.\n"
            "Execute: pip install apscheduler pytz"
        )
        sys.exit(1)

    pub_cfg = _load_publishing_config()
    if not pub_cfg:
        logger.error("publishing.yaml vazio ou nao encontrado. Abortando.")
        sys.exit(1)

    if not pub_cfg.get("global", {}).get("enabled", False):
        logger.warning(
            "Publicacao desabilitada (global.enabled=false em publishing.yaml).\n"
            "Altere para true quando pronto para producao."
        )

    scheduler = BlockingScheduler(timezone="UTC")

    # ── JOB 1: Pipeline de geracao de conteudo ────────────────────────────────
    pj_cfg = pub_cfg.get("pipeline_job", {})
    if pj_cfg.get("enabled", True):
        schedule_time = pj_cfg.get("schedule_time", "06:00")
        hour, minute  = map(int, schedule_time.split(":"))
        scheduler.add_job(
            pipeline_job,
            trigger=CronTrigger(hour=hour, minute=minute, timezone="UTC"),
            args=[pub_cfg],
            id="pipeline_job",
            name="Pipeline — geracao de conteudo",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        logger.info("Pipeline job agendado: %s UTC diariamente", schedule_time)

    # ── JOB 2: Upload YouTube — verifica fila ─────────────────────────────────
    check_interval = pub_cfg.get("global", {}).get(
        "queue_check_interval_minutes", 5
    )
    scheduler.add_job(
        upload_job,
        trigger=IntervalTrigger(minutes=check_interval),
        args=[pub_cfg],
        id="upload_job",
        name="Upload YouTube — verificacao de fila",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=300,
    )
    logger.info("Upload YouTube job: verificando fila a cada %dmin", check_interval)

    # ── JOB 3: Notificacao TikTok — verifica fila ────────────────────────────
    tiktok_cfg = pub_cfg.get("tiktok", {})
    if tiktok_cfg.get("enabled", False) and not tiktok_cfg.get("api_enabled", False):
        scheduler.add_job(
            tiktok_notify_job,
            trigger=IntervalTrigger(minutes=check_interval),
            args=[pub_cfg],
            id="tiktok_notify_job",
            name="TikTok Notifier — verificacao de fila",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        logger.info(
            "TikTok notify job: verificando fila a cada %dmin (modo semi-auto)",
            check_interval
        )
    else:
        logger.info("TikTok notify job: desabilitado (api_enabled=true ou tiktok.enabled=false)")

    # ── JOB 4: Reset de contadores diarios ───────────────────────────────────
    scheduler.add_job(
        reset_daily_counters,
        trigger=CronTrigger(hour=0, minute=0, timezone="UTC"),
        args=[pub_cfg],
        id="reset_job",
        name="Reset — contadores diarios",
        max_instances=1,
    )
    logger.info("Reset job: meia-noite UTC diariamente")

    logger.info("=" * 60)
    logger.info("Scheduler iniciado. Ctrl+C para parar.")
    logger.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler encerrado.")


def setup_logging() -> None:
    log_dir  = _find_base_dir() / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / ("scheduler_" + datetime.now().strftime("%Y%m%d") + ".log")
    fmt      = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )
    # Evita vazar o token do bot Telegram (embutido na URL logada pelo httpx)
    # em logs publicos do GitHub Actions. Ver main.silenciar_loggers_sensiveis.
    for nome in ("httpx", "httpcore", "urllib3", "telegram", "googleapiclient.discovery"):
        logging.getLogger(nome).setLevel(logging.WARNING)


if __name__ == "__main__":
    setup_logging()
    run()