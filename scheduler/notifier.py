"""
scheduler/notifier.py
=====================
Envia kit de postagem TikTok via Telegram Bot.

Semi-automação: bot envia vídeo + metadados prontos,
operador posta manualmente no TikTok (~2 min por vídeo).

Fluxo:
    1. runner.py detecta item pendente na fila TikTok
    2. notifier.send() empacota e envia para o chat correto
    3. Operador recebe no celular: vídeo + título + hashtags
    4. Operador posta no TikTok e responde /ok ou /fail
    5. runner.py processa resposta e atualiza fila

Comandos suportados (enviados pelo operador no Telegram):
    /ok <video_id>    — marca como publicado
    /fail <video_id>  — reagenda para próxima janela
    /skip <video_id>  — descarta sem reagendar
    /status           — resumo da fila por idioma

Este arquivo também expõe:
    - send_admin_alert()      : usado por stages/validator.py para notificar
                                 o operador quando uma etapa de validação
                                 insiste em falhar apos multiplas tentativas.
    - notify_pipeline_result(): avisos de alto nivel sobre o resultado do
                                 pipeline (historia concluida, etapa critica
                                 falhou) — usado por main.py.
"""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── MONTAGEM DA MENSAGEM ──────────────────────────────────────────────────────

def build_kit_message(metadata: dict, language: str, video_id: str) -> str:
    """
    Monta mensagem de notificação com instruções de postagem.
    Formato MarkdownV2 do Telegram.
    """
    title       = metadata.get("title", "")
    hashtags    = metadata.get("hashtags", [])
    description = metadata.get("description", "")

    hashtags_str = " ".join(hashtags) if isinstance(hashtags, list) else str(hashtags)

    # Escapa caracteres especiais do MarkdownV2
    def esc(text: str) -> str:
        special = r"\_*[]()~`>#+-=|{}.!"
        return "".join(f"\\{c}" if c in special else c for c in str(text))

    return (
        f"📱 *TikTok Post Ready* — `{language.upper()}`\n\n"
        f"*Título:*\n`{esc(title)}`\n\n"
        f"*Hashtags:*\n`{esc(hashtags_str)}`\n\n"
        f"*Descrição:*\n{esc(description)}\n\n"
        f"─────────────────\n"
        f"1\\. Baixe o vídeo abaixo\n"
        f"2\\. Abra TikTok → Nova postagem\n"
        f"3\\. Cole o título e hashtags\n"
        f"4\\. Confirme aqui:\n\n"
        f"`/ok {video_id}`  ✅ publicado\n"
        f"`/fail {video_id}`  🔄 reagendar\n"
        f"`/skip {video_id}`  ⏭️ descartar"
    )


# ── ALERTA GENERICO DE ADMIN (usado pelo stages/validator.py) ─────────────────

async def _send_admin_alert_async(message: str, bot_token: str, admin_chat_id: str) -> bool:
    """Envia mensagem de texto simples para o chat de admin."""
    try:
        import telegram
    except ImportError:
        logger.error("[notifier] python-telegram-bot nao instalado — alerta nao enviado")
        return False

    if not bot_token or not admin_chat_id:
        logger.warning("[notifier] TELEGRAM_BOT_TOKEN ou admin_chat_id ausente — alerta nao enviado")
        return False

    try:
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=admin_chat_id, text=message)
        return True
    except Exception as e:
        logger.error("[notifier] Falha ao enviar alerta de admin: %s", e)
        return False


def _resolve_telegram_credentials(config: dict | None) -> tuple[str, str]:
    """
    Resolve bot_token e admin_chat_id a partir de config/settings.yaml
    (com suporte a placeholders "$VAR") ou, na ausencia, das variaveis
    de ambiente TELEGRAM_BOT_TOKEN e TELEGRAM_ADMIN_CHAT_ID diretamente.
    Nunca loga o valor resolvido (evita expor token/chat_id no log).
    """
    config = config or {}
    tg_cfg = config.get("telegram", {})

    bot_token = tg_cfg.get("bot_token", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    admin_chat_id = tg_cfg.get("admin_chat_id", "") or os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "")
    if str(admin_chat_id).startswith("$"):
        admin_chat_id = os.environ.get(admin_chat_id.lstrip("$").strip("{}"), "")

    return bot_token, admin_chat_id


def send_admin_alert(message: str, config: dict | None = None) -> bool:
    """
    Envia um alerta de texto simples (sem video, sem MarkdownV2) para o
    chat de administracao configurado. Usado pelo stages/validator.py
    quando uma etapa nao passa na validacao apos multiplas tentativas, e
    por notify_pipeline_result() para avisos de alto nivel.

    Config esperada (config/settings.yaml), opcional:
        telegram:
          bot_token: "$TELEGRAM_BOT_TOKEN"
          admin_chat_id: "$TELEGRAM_ADMIN_CHAT_ID"

    Se config nao for passado (ou nao tiver os campos), cai para as
    variaveis de ambiente TELEGRAM_BOT_TOKEN e TELEGRAM_ADMIN_CHAT_ID
    diretamente — util para chamadas isoladas fora do fluxo principal
    do pipeline (ex: dentro do validator.py).
    """
    bot_token, admin_chat_id = _resolve_telegram_credentials(config)

    try:
        return asyncio.run(_send_admin_alert_async(message, bot_token, admin_chat_id))
    except RuntimeError as e:
        if "cannot be called from a running event loop" in str(e):
            logger.error("[notifier] Loop asyncio ja ativo — use _send_admin_alert_async diretamente")
            return False
        logger.error("[notifier] RuntimeError ao enviar alerta: %s", e)
        return False


# ── AVISOS DE ALTO NIVEL DO PIPELINE (usado por main.py) ──────────────────────

_EVENT_ICONS = {
    "success": "✅",
    "partial": "⚠️",
    "failure": "❌",
}

_FIELD_LABELS = [
    ("story_title", "Historia"),
    ("language",    "Idioma"),
    ("stage",       "Etapa"),
    ("reason",      "Motivo"),
    ("parts_done",  "Partes concluidas"),
    ("duration",    "Duracao"),
    ("token_usage", "Tokens (validador)"),
]


def notify_pipeline_result(event: str, details: dict, config: dict | None = None) -> bool:
    """
    Envia um aviso de alto nivel sobre o resultado do pipeline — algo que
    hoje so existe no log local e nunca chega no Telegram.

    event:
        "success" — historia concluida (todas as etapas passaram)
        "partial" — historia concluida com ressalvas (ex: idioma pulado)
        "failure" — etapa critica falhou (audio, video, etc — pipeline
                     nao gerou saida utilizavel para aquela parte/idioma)

    details: dict livre, so os campos presentes aparecem na mensagem.
        Chaves reconhecidas: story_title, language, stage, reason,
        parts_done, duration, token_usage.

    Retorna True/False conforme o envio (mesmo comportamento de
    send_admin_alert — nunca lanca excecao, so loga e retorna False).
    """
    icon = _EVENT_ICONS.get(event, "ℹ️")
    lines = [f"{icon} Pipeline — {event.upper()}"]
    for key, label in _FIELD_LABELS:
        value = details.get(key)
        if value:
            lines.append(f"{label}: {value}")
    message = "\n".join(lines)
    return send_admin_alert(message, config)


# ── NOTIFIER PRINCIPAL ────────────────────────────────────────────────────────

class TikTokNotifier:
    """Gerencia envio de notificações TikTok via Telegram Bot."""

    def __init__(self, config: dict):
        tg_cfg = config.get("telegram", {})

        self.bot_token          = tg_cfg.get("bot_token", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
        self.chats: dict        = tg_cfg.get("chats", {})
        self.max_per_day: int   = tg_cfg.get("max_notifications_per_day", 3)
        self.size_limit_mb: int = tg_cfg.get("video_size_limit_mb", 45)
        self.fallback_to_link   = tg_cfg.get("fallback_to_link", True)
        self.base_url: str      = tg_cfg.get("base_url", "").rstrip("/")

        # Resolve variáveis de ambiente nos chat_ids se necessário
        self.chats = {
            lang: os.environ.get(chat_id.lstrip("$").strip("{}"), chat_id)
            if str(chat_id).startswith("$") else chat_id
            for lang, chat_id in self.chats.items()
        }

    def get_chat_id(self, language: str) -> Optional[str]:
        """Retorna chat_id para o idioma especificado."""
        return self.chats.get(language)

    def _file_size_mb(self, path: str) -> float:
        """Retorna tamanho do arquivo em MB."""
        try:
            return os.path.getsize(path) / (1024 * 1024)
        except OSError:
            return 0.0

    async def _send_async(
        self,
        language: str,
        video_path: str,
        metadata: dict,
        video_id: str,
    ) -> bool:
        """Envia notificação assíncrona via Telegram."""
        try:
            import telegram
        except ImportError:
            logger.error("[notifier] python-telegram-bot não instalado. Execute: pip install python-telegram-bot==20.7")
            return False

        chat_id = self.get_chat_id(language)
        if not chat_id:
            logger.error("[notifier] chat_id não configurado para idioma: %s", language)
            return False

        if not self.bot_token:
            logger.error("[notifier] TELEGRAM_BOT_TOKEN não configurado")
            return False

        bot     = telegram.Bot(token=self.bot_token)
        message = build_kit_message(metadata, language, video_id)

        try:
            file_size = self._file_size_mb(video_path)

            if file_size <= self.size_limit_mb:
                # Envia arquivo diretamente
                with open(video_path, "rb") as video_file:
                    await bot.send_video(
                        chat_id=chat_id,
                        video=video_file,
                        caption=message,
                        parse_mode="MarkdownV2",
                        supports_streaming=True,
                        read_timeout=120,
                        write_timeout=120,
                    )
                logger.info("[notifier] Vídeo enviado: %s (%s) — %.1fMB", video_id, language, file_size)

            elif self.fallback_to_link and self.base_url:
                # Arquivo grande — envia link para download
                rel_path = os.path.relpath(video_path, start=".")
                link     = f"{self.base_url}/{rel_path}".replace("\\", "/")

                def esc(text: str) -> str:
                    special = r"\_*[]()~`>#+-=|{}.!"
                    return "".join(f"\\{c}" if c in special else c for c in str(text))

                link_message = message + f"\n\n📥 [Download do vídeo]({esc(link)})"
                await bot.send_message(
                    chat_id=chat_id,
                    text=link_message,
                    parse_mode="MarkdownV2",
                )
                logger.info("[notifier] Link enviado: %s (%s) — %.1fMB (acima do limite)", video_id, language, file_size)

            else:
                logger.warning(
                    "[notifier] Vídeo muito grande (%.1fMB) e fallback não configurado — %s",
                    file_size, video_id
                )
                return False

            return True

        except telegram.error.TimedOut:
            logger.warning("[notifier] Timeout ao enviar %s — arquivo grande, tente aumentar timeout", video_id)
            return False
        except telegram.error.TelegramError as e:
            logger.error("[notifier] Erro Telegram para %s: %s", video_id, e)
            return False
        except FileNotFoundError:
            logger.error("[notifier] Arquivo não encontrado: %s", video_path)
            return False

    def send(
        self,
        language: str,
        video_path: str,
        metadata: dict,
        video_id: str,
        max_retries: int = 3,
    ) -> bool:
        """
        Interface síncrona com retry automático.
        Retorna True se enviado com sucesso, False caso contrário.
        """
        for attempt in range(1, max_retries + 1):
            try:
                result = asyncio.run(
                    self._send_async(language, video_path, metadata, video_id)
                )
                if result:
                    return True
                logger.warning(
                    "[notifier] Tentativa %d/%d falhou para %s",
                    attempt, max_retries, video_id
                )
            except RuntimeError as e:
                # asyncio.run() não pode ser chamado dentro de loop existente
                if "cannot be called from a running event loop" in str(e):
                    logger.error("[notifier] Loop asyncio já ativo — use _send_async diretamente")
                    return False
                logger.error("[notifier] RuntimeError na tentativa %d: %s", attempt, e)
            except Exception as e:
                logger.error("[notifier] Exceção na tentativa %d/%d: %s", attempt, max_retries, e)

        logger.error("[notifier] Todas as %d tentativas falharam para %s", max_retries, video_id)
        return False


# ── HANDLER DE COMANDOS TELEGRAM ─────────────────────────────────────────────

async def handle_telegram_command(update, context) -> None:
    """
    Processa comandos enviados pelo operador após postagem manual.

    Comandos:
        /ok <video_id>    — marca como publicado
        /fail <video_id>  — reagenda para próxima janela
        /skip <video_id>  — descarta sem reagendar
        /status           — resumo da fila por idioma
    """
    from scheduler import queue as queue_module

    text  = update.message.text.strip()
    parts = text.split()

    if not parts:
        return

    command = parts[0].lower()

    # ── /status (sem video_id) ────────────────────────────────────────────────
    if command == "/status":
        lines = ["📊 *Status da Fila TikTok*\n"]
        for lang in ["pt-br", "en", "es"]:
            summary = queue_module.get_queue_summary(lang)
            by_status = summary.get("by_status", {})
            lines.append(
                f"*{lang.upper()}*\n"
                f"  ⏳ Pendentes: {by_status.get('pending', 0)}\n"
                f"  📤 Enviados hoje: {summary.get('uploads_today', 0)}\n"
                f"  ✅ Publicados: {by_status.get('uploaded', 0)}\n"
                f"  ❌ Falhos: {by_status.get('failed', 0)}\n"
            )
        await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
        return

    # ── Comandos que requerem video_id ────────────────────────────────────────
    if len(parts) < 2:
        await update.message.reply_text(
            "❌ Formato inválido\\.\n\n"
            "Use:\n`/ok video_id`\n`/fail video_id`\n`/skip video_id`",
            parse_mode="MarkdownV2"
        )
        return

    video_id = parts[1]

    # Detecta idioma a partir da fila
    language = _find_language_for_item(video_id, queue_module)

    if command == "/ok":
        if language:
            queue_module.update_status(language, video_id, "youtube", "uploaded")
            queue_module.update_status(language, video_id, "tiktok",  "uploaded")
        await update.message.reply_text(
            f"✅ Marcado como publicado: `{video_id}`",
            parse_mode="Markdown"
        )
        logger.info("[notifier] /ok recebido para %s", video_id)

    elif command == "/fail":
        if language:
            queue_module.update_status(language, video_id, "youtube", "failed")
            queue_module.update_status(language, video_id, "tiktok",  "failed")
        await update.message.reply_text(
            f"🔄 Reagendado para próxima janela: `{video_id}`",
            parse_mode="Markdown"
        )
        logger.info("[notifier] /fail recebido para %s", video_id)

    elif command == "/skip":
        if language:
            queue_module.update_status(language, video_id, "youtube", "cancelled")
            queue_module.update_status(language, video_id, "tiktok",  "cancelled")
        await update.message.reply_text(
            f"⏭️ Item descartado: `{video_id}`",
            parse_mode="Markdown"
        )
        logger.info("[notifier] /skip recebido para %s", video_id)

    else:
        await update.message.reply_text(
            "❓ Comando não reconhecido\\.\n\n"
            "Comandos válidos: `/ok` `/fail` `/skip` `/status`",
            parse_mode="MarkdownV2"
        )


def _find_language_for_item(video_id: str, queue_module) -> Optional[str]:
    """
    Busca o idioma de um item pelo video_id em todas as filas.
    Retorna None se não encontrado.
    """
    for lang in ["pt-br", "en", "es"]:
        try:
            queue = queue_module._load_queue(lang)
            for item in queue.get("items", []):
                if item.get("id") == video_id:
                    return lang
        except Exception:
            continue
    return None