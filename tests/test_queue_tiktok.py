import pytest
from pathlib import Path
from unittest.mock import patch

@pytest.fixture(autouse=True)
def use_temp_queue(tmp_path, monkeypatch):
    import scheduler.queue as q
    monkeypatch.setattr(q, "_QUEUE_DIR_PATHS", [tmp_path])

import scheduler.queue as queue_module

@pytest.fixture
def fake_video(tmp_path):
    """Cria um arquivo de video fake que realmente existe no disco."""
    video = tmp_path / "video_001.mp4"
    video.write_bytes(b"fake video content")
    return video

@pytest.fixture
def fake_video_2(tmp_path):
    video = tmp_path / "video_002.mp4"
    video.write_bytes(b"fake video content 2")
    return video

def test_enqueue_creates_pending_item(fake_video):
    queue_module.enqueue("pt-br", fake_video, None, {"tiktok_title": "Teste"}, "Teste")
    items = queue_module.get_pending("pt-br")
    assert len(items) == 1
    assert items[0]["status"] == "pending"

def test_update_status_uploaded(fake_video):
    queue_module.enqueue("pt-br", fake_video, None, {}, "Teste")
    item_id = queue_module.get_pending("pt-br")[0]["id"]
    queue_module.update_status("pt-br", item_id, "youtube", "uploaded")
    queue_module.update_status("pt-br", item_id, "tiktok", "uploaded")
    from scheduler.queue import _load_queue
    q = _load_queue("pt-br")
    item = next(i for i in q["items"] if i["id"] == item_id)
    assert item["status"] == "uploaded"

def test_update_status_failed_increments_attempts(fake_video_2):
    queue_module.enqueue("pt-br", fake_video_2, None, {}, "Teste2")
    item_id = queue_module.get_pending("pt-br")[0]["id"]
    queue_module.update_status("pt-br", item_id, "youtube", "failed")
    queue_module.update_status("pt-br", item_id, "tiktok", "failed")
    from scheduler.queue import _load_queue
    q = _load_queue("pt-br")
    item = next(i for i in q["items"] if i["id"] == item_id)
    assert item["attempts"] == 1

def test_count_uploads_today(tmp_path):
    video = tmp_path / "video_003.mp4"
    video.write_bytes(b"fake")
    queue_module.enqueue("en", video, None, {}, "Test3")
    item_id = queue_module.get_pending("en")[0]["id"]
    queue_module.update_status("en", item_id, "youtube", "uploaded")
    queue_module.update_status("en", item_id, "tiktok", "uploaded")
    assert queue_module.count_uploads_today("en") == 1

def test_reset_daily_counter(tmp_path):
    video = tmp_path / "video_004.mp4"
    video.write_bytes(b"fake")
    queue_module.enqueue("es", video, None, {}, "Test4")
    item_id = queue_module.get_pending("es")[0]["id"]
    queue_module.update_status("es", item_id, "youtube", "uploaded")
    queue_module.update_status("es", item_id, "tiktok", "uploaded")
    queue_module.reset_daily_counter("es")
    assert queue_module.count_uploads_today("es") == 0