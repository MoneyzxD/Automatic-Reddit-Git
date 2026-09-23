import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from googleapiclient.errors import HttpError

from scheduler import queue as queue_module
from scheduler import uploader as uploader_module


@pytest.fixture
def upload_context(tmp_path, monkeypatch):
    monkeypatch.setattr(queue_module, "_QUEUE_DIR_PATHS", [tmp_path / "queue"])
    monkeypatch.setattr(uploader_module, "_think_time", lambda: None)
    # O servico simulado guarda os argumentos; nao deve manter um arquivo
    # real aberto pelo MediaFileUpload e impedir a limpeza no Windows.
    monkeypatch.setattr(
        "googleapiclient.http.MediaFileUpload",
        lambda filename, **kwargs: SimpleNamespace(filename=filename, **kwargs),
    )
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video de teste")
    thumbnail = tmp_path / "thumbnail.jpg"
    thumbnail.write_bytes(b"thumbnail de teste")
    item_id = queue_module.enqueue("pt", video, thumbnail, {}, "Titulo de teste")
    item = queue_module.get_pending("pt")[0]
    service = MagicMock()
    service.videos.return_value.insert.return_value.next_chunk.return_value = (
        None, {"id": "video-ja-enviado"}
    )
    youtube = uploader_module.YouTubeUploader("nao-usado.json", "nao-usado.json")
    youtube._service = service
    uploader = uploader_module.Uploader.__new__(uploader_module.Uploader)
    uploader.language = "pt"
    uploader.channel_config = {}
    uploader.pub_config = {
        "global": {"platforms": ["youtube"], "delete_after_upload": True},
        "post_upload_edit": {"enabled": False},
    }
    uploader.youtube = youtube
    uploader.tiktok = None
    return SimpleNamespace(
        item_id=item_id, item=item, video=video, thumbnail=thumbnail,
        service=service, youtube=youtube, uploader=uploader,
    )


def _thumbnail_forbidden(context):
    erro = HttpError(
        SimpleNamespace(status=403, reason="Forbidden"),
        json.dumps({"error": {
            "message": "The authenticated user doesn't have permissions to upload and set custom video thumbnails.",
            "errors": [{"reason": "forbidden"}],
        }}).encode(),
    )
    context.service.thumbnails.return_value.set.return_value.execute.side_effect = erro


def test_thumbnail_403_nao_transforma_video_enviado_em_falha(upload_context, caplog):
    _thumbnail_forbidden(upload_context)

    result = upload_context.youtube.upload(upload_context.item)

    assert result["status"] == "uploaded"
    assert result["video_id"] == "video-ja-enviado"
    assert result["thumbnail"]["status"] == "failed"
    assert "permissions" in result["thumbnail"]["error"]
    assert "studio.youtube.com/video/video-ja-enviado/edit" in caplog.text
    assert "verificacao" in caplog.text


@pytest.mark.parametrize("thumbnail_failure", ["forbidden", "missing"])
def test_falha_thumbnail_preserva_midia_e_status_sem_reenfileirar_video(
    upload_context, thumbnail_failure
):
    if thumbnail_failure == "forbidden":
        _thumbnail_forbidden(upload_context)
    else:
        upload_context.thumbnail.unlink()

    result = upload_context.uploader.upload_item(
        upload_context.item, publish_at="2030-01-01T12:00:00Z"
    )["youtube"]
    saved = queue_module._load_queue("pt")["items"][0]

    assert result["status"] == "uploaded"
    expected = "failed" if thumbnail_failure == "forbidden" else "missing"
    assert result["thumbnail"]["status"] == expected
    assert saved["platforms"]["youtube"]["thumbnail"] == result["thumbnail"]
    assert saved["platforms"]["youtube"]["video_id"] == "video-ja-enviado"
    assert saved["platforms"]["youtube"]["status"] == "uploaded"
    assert saved["platforms"]["youtube"]["publish_at"] == "2030-01-01T12:00:00Z"
    assert saved["video_path"] == str(upload_context.video)
    assert saved["thumbnail_path"] == str(upload_context.thumbnail)
    assert upload_context.video.exists()
    if thumbnail_failure == "forbidden":
        assert upload_context.thumbnail.exists()
    assert queue_module.get_pending("pt") == []
    assert queue_module.get_failed("pt") == []
    upload_context.service.videos.return_value.insert.assert_called_once()


def test_sucesso_thumbnail_mantem_limpeza_apos_upload(upload_context):
    result = upload_context.uploader.upload_item(
        upload_context.item, publish_at="2030-01-01T12:00:00Z"
    )["youtube"]
    saved = queue_module._load_queue("pt")["items"][0]

    assert result["thumbnail"]["status"] == "uploaded"
    assert saved["platforms"]["youtube"]["thumbnail"]["status"] == "uploaded"
    assert saved["video_path"] is None
    assert saved["thumbnail_path"] is None
    assert not upload_context.video.exists()
    assert not upload_context.thumbnail.exists()


def test_thumbnail_nao_solicitada_nao_dispara_chamada_api(upload_context):
    upload_context.item["thumbnail_path"] = None

    result = upload_context.youtube.upload(upload_context.item)

    assert result["status"] == "uploaded"
    assert result["thumbnail"]["status"] == "not_requested"
    upload_context.service.thumbnails.assert_not_called()
