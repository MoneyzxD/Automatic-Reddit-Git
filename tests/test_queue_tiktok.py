import pytest
from pathlib import Path
from unittest.mock import patch

@pytest.fixture(autouse=True)
def use_temp_queue(tmp_path, monkeypatch):
    import scheduler.queue as q
    monkeypatch.setattr(q, "_QUEUE_DIR_PATHS", [tmp_path])

import scheduler.queue as queue_module


def test_fila_corrompida_nao_vira_fila_vazia(tmp_path):
    path = tmp_path / "pt.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(queue_module.QueueStateError):
        queue_module.get_pending("pt")
    assert path.read_text(encoding="utf-8") == "{broken"


def batch_items(fake_video, fake_video_2):
    return [dict(video_path=path, thumbnail_path=None, metadata={"narrator_profile_id": "p1"},
                 title="Título", story_id="s1", part=part, total=2)
            for part, path in enumerate([fake_video, fake_video_2], 1)]


def test_batch_repetido_retorna_mesmos_ids(fake_video, fake_video_2):
    items = batch_items(fake_video, fake_video_2)
    first = queue_module.enqueue_many("pt", items, generation_key="a" * 64)
    assert queue_module.enqueue_many("pt", items, generation_key="a" * 64) == first
    assert len(queue_module.get_pending("pt")) == 2


def test_batch_conflitante_nao_substitui_item_existente(fake_video, fake_video_2, tmp_path):
    items = batch_items(fake_video, fake_video_2)
    queue_module.enqueue_many("pt", items, generation_key="a" * 64)
    before = (tmp_path / "pt.json").read_bytes()
    with pytest.raises(queue_module.QueueStateError):
        queue_module.enqueue_many("pt", [{**item, "title": "Alterado"} for item in items], generation_key="a" * 64)
    assert (tmp_path / "pt.json").read_bytes() == before


def test_batch_arquivo_ausente_nao_enfileira_primeira_parte(fake_video, fake_video_2, tmp_path):
    fake_video_2.unlink()
    with pytest.raises(queue_module.QueueStateError):
        queue_module.enqueue_many("pt", batch_items(fake_video, fake_video_2), generation_key="a" * 64)
    assert not (tmp_path / "pt.json").exists()


def test_erro_replace_preserva_fila_anterior(fake_video, fake_video_2, tmp_path, monkeypatch):
    queue_module.enqueue("pt", fake_video, None, {}, "Anterior")
    before = (tmp_path / "pt.json").read_bytes()
    def disk_full(*args):
        raise OSError("disco cheio")
    monkeypatch.setattr(queue_module.os, "replace", disk_full)
    with pytest.raises(queue_module.QueueStateError):
        queue_module.enqueue_many("pt", batch_items(fake_video, fake_video_2), generation_key="a" * 64)
    assert (tmp_path / "pt.json").read_bytes() == before

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


def test_count_uploads_today_nao_depende_do_tiktok(tmp_path):
    video = tmp_path / "video_youtube.mp4"
    video.write_bytes(b"fake")
    queue_module.enqueue("en", video, None, {}, "So YouTube")
    item_id = queue_module.get_pending("en")[0]["id"]

    queue_module.update_status("en", item_id, "youtube", "uploaded")

    assert queue_module.count_uploads_today("en") == 1


def test_agendamento_conta_na_data_local_do_canal(tmp_path):
    video = tmp_path / "video_agendado.mp4"
    video.write_bytes(b"fake")
    queue_module.enqueue("en", video, None, {}, "Agendado")
    item_id = queue_module.get_pending("en")[0]["id"]

    queue_module.update_status(
        "en",
        item_id,
        "youtube",
        "uploaded",
        publish_at="2030-01-02T01:00:00Z",
    )

    assert queue_module.count_scheduled_by_local_date(
        "en", "America/New_York",
    ) == {"2030-01-01": 1}

def test_reset_daily_counter(tmp_path):
    video = tmp_path / "video_004.mp4"
    video.write_bytes(b"fake")
    queue_module.enqueue("es", video, None, {}, "Test4")
    item_id = queue_module.get_pending("es")[0]["id"]
    queue_module.update_status("es", item_id, "youtube", "uploaded")
    queue_module.update_status("es", item_id, "tiktok", "uploaded")
    queue_module.reset_daily_counter("es")
    assert queue_module.count_uploads_today("es") == 0
