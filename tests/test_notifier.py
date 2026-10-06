import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest
from scheduler.notifier import TikTokNotifier, build_kit_message
from scheduler.notifier import handle_telegram_command
from scheduler import queue as queue_module


class MensagemOperador:
    def __init__(self, text):
        self.text = text
        self.respostas = []

    async def reply_text(self, text, **kwargs):
        self.respostas.append(text)


@pytest.mark.parametrize("language", ["pt", "pt-br", "en", "es"])
@pytest.mark.parametrize("youtube_status", ["pending", "uploading", "uploaded"])
@pytest.mark.parametrize("command,status", [
    ("/ok", "uploaded"), ("/fail", "failed"), ("/skip", "cancelled"),
])
def test_comando_tiktok_preserva_estado_youtube(
    tmp_path, monkeypatch, language, youtube_status, command, status,
):
    # Regressão: confirmar o kit manual não pode confirmar/reiniciar o YouTube.
    monkeypatch.setattr(queue_module, "_QUEUE_DIR_PATHS", [tmp_path])
    monkeypatch.delenv("PIPELINE_STATE_REQUIRED", raising=False)
    video = tmp_path / "kit.mp4"
    video.write_bytes(b"video isolado")
    item_id = queue_module.enqueue(language, video, None, {}, "História")
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    if youtube_status == "uploaded":
        queue_module.update_status(
            language, item_id, "youtube", "uploaded", video_id="id-confirmado",
            url="https://www.youtube.com/watch?v=id-confirmado",
            publish_at="2026-10-07T12:00:00Z",
            thumbnail={"status": "failed", "error": "403"},
        )
    elif youtube_status == "uploading":
        queue_module.update_status(language, item_id, "youtube", "uploading")
    before = deepcopy(queue_module.get_item(language, item_id))
    count_before = queue_module.count_uploads_today(language)
    last_before = queue_module.get_last_upload_time(language)
    message = MensagemOperador(f"{command} {item_id}")

    asyncio.run(handle_telegram_command(SimpleNamespace(message=message), None))

    after = queue_module.get_item(language, item_id)
    assert after["platforms"]["tiktok"]["status"] == status
    assert after["platforms"]["youtube"] == before["platforms"]["youtube"]
    assert after["schedule"] == before["schedule"]
    assert queue_module.count_uploads_today(language) == count_before
    assert queue_module.get_last_upload_time(language) == last_before
    if youtube_status == "pending":
        assert item_id in {item["id"] for item in queue_module.get_pending(language)}
    assert message.respostas


def test_build_kit_message_contains_title():
    metadata = {
        "title": "Eu fiz isso e me arrependi",
        "hashtags": ["#reddit", "#historias"],
        "description": "Uma história incrível sobre família."
    }
    msg = build_kit_message(metadata, language="pt-br", video_id="video_001")
    assert "Eu fiz isso e me arrependi" in msg
    assert "#reddit" in msg
    assert "PT-BR" in msg


def test_build_kit_message_contains_commands():
    metadata = {"title": "Test", "hashtags": ["#test"], "description": "desc"}
    msg = build_kit_message(metadata, language="en", video_id="video_002")
    assert "/ok video_002" in msg
    assert "/fail video_002" in msg
    assert "/skip video_002" in msg


def test_build_kit_message_mostra_horario_planejado():
    metadata = {
        "title": "Test",
        "hashtags": ["#test"],
        "description": "desc",
        "scheduled_for": "24/09/2026 12:00 (America/Sao_Paulo)",
    }

    msg = build_kit_message(metadata, language="pt", video_id="video_003")

    assert "Publicar em" in msg
    assert "24/09/2026 12:00" in msg


def test_notifier_loads_config():
    config = {
        "telegram": {
            "bot_token": "fake_token",
            "chats": {"pt-br": "123456"},
            "max_notifications_per_day": 3,
            "video_size_limit_mb": 45,
            "fallback_to_link": True,
            "base_url": "http://localhost:8080"
        }
    }
    notifier = TikTokNotifier(config=config)
    assert notifier.max_per_day == 3
    assert notifier.size_limit_mb == 45
    assert notifier.fallback_to_link is True


def test_get_chat_id_returns_correct_id():
    config = {
        "telegram": {
            "bot_token": "fake_token",
            "chats": {"pt-br": "111", "en": "222", "es": "333"},
            "max_notifications_per_day": 3,
            "video_size_limit_mb": 45,
            "fallback_to_link": False,
            "base_url": ""
        }
    }
    notifier = TikTokNotifier(config=config)
    assert notifier.get_chat_id("pt-br") == "111"
    assert notifier.get_chat_id("en") == "222"
    assert notifier.get_chat_id("es") == "333"
    assert notifier.get_chat_id("fr") is None


def test_file_size_mb_missing_file():
    config = {"telegram": {"bot_token": "", "chats": {}, "max_notifications_per_day": 3,
                           "video_size_limit_mb": 45, "fallback_to_link": False, "base_url": ""}}
    notifier = TikTokNotifier(config=config)
    assert notifier._file_size_mb("/nao/existe.mp4") == 0.0
