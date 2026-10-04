"""Confirmação antes de capa/limpeza; resultado incerto nunca é reenviado."""
from types import SimpleNamespace
from unittest.mock import MagicMock
import json

import pytest

from scheduler import queue, uploader as module
from utils.pipeline_state import StateError


@pytest.fixture
def youtube_fake(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [tmp_path / "data/queue"])
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "production")
    monkeypatch.setattr(module, "_think_time", lambda: None)
    monkeypatch.setattr("googleapiclient.http.MediaFileUpload", lambda filename, **kwargs: SimpleNamespace(filename=filename))
    from scheduler import notifier
    monkeypatch.setattr(notifier, "send_admin_alert", lambda *args, **kwargs: True)
    video = tmp_path / "data/exports/pt/a.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    thumbnail = video.with_suffix(".jpg")
    thumbnail.write_bytes(b"image")
    item_id = queue.enqueue("pt", video, thumbnail, {}, "Title", story_id="s1")
    item = queue.get_pending("pt")[0]
    events = []
    service = MagicMock()
    service.videos.return_value.insert.return_value.next_chunk.return_value = (None, {"id": "vid1"})
    service.thumbnails.return_value.set.return_value.execute.side_effect = lambda: events.append("thumbnail")
    yt = module.YouTubeUploader.__new__(module.YouTubeUploader)
    yt._service = service
    wrapper = module.Uploader.__new__(module.Uploader)
    wrapper.language, wrapper.channel_config, wrapper.youtube, wrapper.tiktok = "pt", {}, yt, None
    wrapper.base_dir = tmp_path
    wrapper.pub_config = {"global": {"platforms": ["youtube"], "delete_after_upload": False},
                          "post_upload_edit": {"enabled": False}}
    return SimpleNamespace(uploader=yt, wrapper=wrapper, item=item, item_id=item_id, events=events,
                           video=video, thumbnail=thumbnail, service=service, root=tmp_path)


def test_callback_vem_antes_da_thumbnail(youtube_fake):
    ctx = youtube_fake
    def checkpoint(result):
        assert result["video_id"] == "vid1"
        ctx.events.append("checkpoint")
    assert ctx.uploader.upload(ctx.item, on_video_uploaded=checkpoint)["status"] == "uploaded"
    assert ctx.events == ["checkpoint", "thumbnail"]


@pytest.mark.parametrize("exception", [StateError, OSError])
def test_callback_falho_nao_e_engolido_apos_video_aceito(youtube_fake, exception):
    ctx = youtube_fake
    def failed(result):
        ctx.events.append("checkpoint")
        assert result["video_id"] == "vid1"
        raise exception("SYNTHETIC_TOKEN")
    with pytest.raises(StateError):
        ctx.uploader.upload(ctx.item, on_video_uploaded=failed)
    assert ctx.events == ["checkpoint"]


def test_wrapper_grava_confirmacao_antes_da_capa(youtube_fake, monkeypatch):
    ctx = youtube_fake
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    def save(root, *, reason):
        current = queue._load_queue("pt")["items"][0]["platforms"]["youtube"]
        if reason == "youtube_video_confirmed":
            assert current["video_id"] == "vid1" and current["status"] == "uploaded"
            assert ctx.video.exists()
        ctx.events.append("save:" + reason)
        return {}
    monkeypatch.setattr(module, "checkpoint_from_environment", save, raising=False)
    ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert ctx.events[:3] == ["save:before_youtube_upload", "save:youtube_video_confirmed", "thumbnail"]
    assert ctx.events[-1] == "save:youtube_thumbnail"


def test_checkpoint_confirmacao_falho_impede_capa_limpeza_e_reenvio(youtube_fake, monkeypatch):
    ctx = youtube_fake
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    ctx.wrapper.pub_config["global"]["delete_after_upload"] = True
    def save(root, *, reason):
        if reason == "youtube_video_confirmed":
            raise StateError("synthetic")
        return {}
    monkeypatch.setattr(module, "checkpoint_from_environment", save, raising=False)
    with pytest.raises(StateError):
        ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert ctx.events == []
    assert ctx.video.exists()
    assert queue.get_item("pt", ctx.item_id)["platforms"]["youtube"]["video_id"] == "vid1"
    ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    ctx.service.videos.return_value.insert.assert_called_once()


def test_checkpoint_previo_falho_nao_chama_youtube(youtube_fake, monkeypatch):
    ctx = youtube_fake
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    def fail(*args, **kwargs):
        raise StateError("synthetic")
    monkeypatch.setattr(module, "checkpoint_from_environment", fail, raising=False)
    with pytest.raises(StateError):
        ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    ctx.service.videos.assert_not_called()
    assert queue.get_uncertain("pt")[0]["id"] == ctx.item_id


def test_resultado_incertro_bloqueia_segunda_tentativa(youtube_fake):
    ctx = youtube_fake
    ctx.service.videos.return_value.insert.return_value.next_chunk.side_effect = ConnectionError("SYNTHETIC_TOKEN")
    result = ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert result["youtube"]["status"] == "uncertain"
    assert queue.get_uncertain("pt")[0]["id"] == ctx.item_id
    with pytest.raises(StateError):
        ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    ctx.service.videos.return_value.insert.assert_called_once()


@pytest.mark.parametrize("response", [{}, {"id": None}, {"id": ""}, {"id": "invalid/url"}])
def test_resposta_sem_id_valido_e_incerteza_nao_sucesso(youtube_fake, response):
    ctx = youtube_fake
    ctx.service.videos.return_value.insert.return_value.next_chunk.return_value = (None, response)
    result = ctx.uploader.upload(ctx.item)
    assert result["status"] == "uncertain"
    ctx.service.thumbnails.assert_not_called()


def test_oauth_preflight_indisponivel_conserva_midia_pendente(youtube_fake, monkeypatch):
    ctx = youtube_fake
    def unavailable():
        raise RuntimeError("SYNTHETIC_TOKEN")
    monkeypatch.setattr(ctx.uploader, "_get_service", unavailable)
    result = ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert result["youtube"]["status"] == "failed"
    assert queue.get_pending("pt")[0]["id"] == ctx.item_id
    assert queue.get_uncertain("pt") == []
    ctx.service.videos.assert_not_called()
    assert ctx.video.exists()


def test_uploaded_repetido_nao_muda_timestamp_contador_ou_id(youtube_fake, monkeypatch):
    ctx = youtube_fake
    queue.update_status("pt", ctx.item_id, "youtube", "uploaded", video_id="vid1", url="https://youtu.be/vid1")
    prior = queue._load_queue("pt")
    monkeypatch.setattr(queue, "_now_iso", lambda: "2099-01-01T00:00:00+00:00")
    queue.update_status("pt", ctx.item_id, "youtube", "uploaded", thumbnail={"status": "failed"})
    current = queue._load_queue("pt")
    assert current["items"][0]["platforms"]["youtube"]["video_id"] == "vid1"
    assert current["items"][0]["platforms"]["youtube"]["uploaded_at"] == prior["items"][0]["platforms"]["youtube"]["uploaded_at"]
    assert current["items"][0]["schedule"]["uploaded_at"] == prior["items"][0]["schedule"]["uploaded_at"]
    assert current["uploads_today"] == prior["uploads_today"] == 1


@pytest.mark.parametrize("state", ["uploaded", "uploading"])
def test_upload_nao_retorna_pending_implicitamente(youtube_fake, state):
    ctx = youtube_fake
    queue.update_status("pt", ctx.item_id, "youtube", state, video_id="vid1" if state == "uploaded" else None)
    prior = (ctx.root / "data/queue/pt.json").read_bytes()
    with pytest.raises(queue.QueueStateError):
        queue.update_status("pt", ctx.item_id, "youtube", "pending")
    assert (ctx.root / "data/queue/pt.json").read_bytes() == prior


def test_thumbnail_403_nao_repete_upload(youtube_fake):
    from googleapiclient.errors import HttpError
    ctx = youtube_fake
    error = HttpError(SimpleNamespace(status=403, reason="Forbidden"), b'{"error":{"message":"SYNTHETIC_TOKEN"}}')
    ctx.service.thumbnails.return_value.set.return_value.execute.side_effect = error
    first = ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert first["youtube"]["status"] == "uploaded"
    ctx.service.videos.return_value.insert.assert_called_once()
    assert ctx.video.exists()


def test_erros_do_youtube_nao_vazam_body_em_logs(youtube_fake, caplog):
    ctx = youtube_fake
    ctx.service.videos.return_value.insert.return_value.next_chunk.side_effect = ConnectionError("SYNTHETIC_TOKEN")
    result = ctx.uploader.upload(ctx.item)
    assert "SYNTHETIC" not in json.dumps(result)
    assert "SYNTHETIC" not in caplog.text


def test_fila_pendente_sem_midia_nao_e_contada_como_vazia(youtube_fake):
    ctx = youtube_fake
    ctx.video.unlink()
    with pytest.raises(queue.QueueStateError):
        queue.get_pending("pt")


def test_reset_preserva_historico_confirmado(youtube_fake):
    ctx = youtube_fake
    queue.update_status("pt", ctx.item_id, "youtube", "uploaded", video_id="vid1")
    prior = queue._load_queue("pt")["items"][0]["platforms"]["youtube"]["uploaded_at"]
    queue.reset_daily_counter("pt")
    assert queue._load_queue("pt")["items"][0]["platforms"]["youtube"]["uploaded_at"] == prior
    assert queue.count_uploads_today("pt") == 1


def publishing_config():
    windows = {day: {"start": "00:00", "end": "23:59"} for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    return {"channels": {"pt": {"enabled": True, "timezone": "UTC", "posting_windows_by_weekday": windows}},
            "daily_video_plan": {"enabled": True, "target_per_language": 3, "maximum_target_per_language": 10,
                                 "max_carryover_parts_next_day": 1, "interval_minutes_by_target": {3: 90}}}


def test_publicador_bloqueia_idioma_com_envio_incertro(youtube_fake):
    import publish
    ctx = youtube_fake
    queue.update_status("pt", ctx.item_id, "youtube", "uploading")
    with pytest.raises(StateError):
        publish.publicar_idioma("pt", publishing_config(), maximo=3)
    ctx.service.videos.assert_not_called()


def test_publicador_nao_engole_falha_de_confirmacao(youtube_fake, monkeypatch):
    import publish
    ctx = youtube_fake
    monkeypatch.setattr(publish, "BASE_DIR", ctx.root)
    monkeypatch.setattr(publish, "_enviar_kit_tiktok", lambda *args, **kwargs: False)
    def fail(item, **kwargs):
        queue.update_status("pt", item["id"], "youtube", "uploading")
        raise StateError("synthetic")
    monkeypatch.setattr(ctx.wrapper, "upload_item", fail)
    monkeypatch.setattr(module, "Uploader", lambda *args: ctx.wrapper)
    with pytest.raises(StateError):
        publish.publicar_idioma("pt", publishing_config(), maximo=3)
    assert queue.get_uncertain("pt")[0]["id"] == ctx.item_id


def test_limpeza_so_depois_de_confirmacoes_duraveis(youtube_fake, monkeypatch):
    ctx = youtube_fake
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    queue.update_status("pt", ctx.item_id, "tiktok", "uploading")
    ctx.wrapper.pub_config["global"]["delete_after_upload"] = True
    def save(root, *, reason):
        if reason == "youtube_cleanup":
            assert not ctx.video.exists()
        else:
            assert ctx.video.exists()
        ctx.events.append("save:" + reason)
        return {}
    monkeypatch.setattr(module, "checkpoint_from_environment", save)
    ctx.wrapper.upload_item(ctx.item, publish_at="2030-01-01T12:00:00Z")
    assert ctx.events == ["save:before_youtube_upload", "save:youtube_video_confirmed", "thumbnail",
                          "save:youtube_thumbnail", "save:youtube_cleanup"]


def test_sem_youtube_ativo_nao_apaga_midia_pendente(youtube_fake):
    ctx = youtube_fake
    ctx.wrapper.youtube = None
    ctx.wrapper.pub_config["global"]["delete_after_upload"] = True
    assert ctx.wrapper.upload_item(ctx.item) == {}
    assert ctx.video.exists()
    assert queue.get_pending("pt")[0]["id"] == ctx.item_id


def test_scheduler_nao_engole_state_error_nem_inicia_retry(youtube_fake, monkeypatch):
    from scheduler import runner
    ctx = youtube_fake
    def fail(*args, **kwargs):
        raise StateError("synthetic")
    monkeypatch.setattr(ctx.wrapper, "upload_item", fail)
    monkeypatch.setattr(module, "Uploader", lambda *args: ctx.wrapper)
    monkeypatch.setattr(runner, "_can_upload", lambda *args: (True, ""))
    monkeypatch.setattr(runner.random, "uniform", lambda *args: 0)
    monkeypatch.setattr(runner.time, "sleep", lambda *args: None)
    config = {**publishing_config(), "global": {"platforms": ["youtube"]}}
    with pytest.raises(StateError):
        runner.upload_job(config)
    assert queue.get_item("pt", ctx.item_id)["attempts"] == 0


@pytest.mark.parametrize("caller", ["wrapper", "publish"])
def test_namespace_validacao_nao_publica(youtube_fake, monkeypatch, caller):
    import publish
    ctx = youtube_fake
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setattr(publish, "require_ready", lambda *args: {})
    monkeypatch.setattr(module, "checkpoint_from_environment", lambda *args, **kwargs: {})
    monkeypatch.setattr(publish, "_enviar_kit_tiktok", lambda *args, **kwargs: False)
    monkeypatch.setattr(module, "Uploader", lambda *args: ctx.wrapper)
    with pytest.raises(StateError):
        if caller == "wrapper":
            ctx.wrapper.upload_item(ctx.item)
        else:
            publish.publicar_idioma("pt", publishing_config(), maximo=3)
    ctx.service.videos.assert_not_called()
