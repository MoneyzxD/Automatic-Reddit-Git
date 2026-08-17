import pytest
from scheduler.notifier import TikTokNotifier, build_kit_message


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