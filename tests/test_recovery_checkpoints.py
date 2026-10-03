"""Fonte/checkpoints privados e exportação atômica por idioma."""
import json
from pathlib import Path

import pytest

from stages.narrator_profile import source_sha256


STORY = {"id": "s1", "title": "Source", "text": "I am a man."}


def test_fonte_original_round_trip(tmp_path):
    from utils.pipeline_recovery import save_source, load_source
    digest = source_sha256("Source", "I am a man.")
    save_source(tmp_path, STORY, digest, expanded_source="I am a man.")
    assert load_source(tmp_path, "s1", digest)["story"] == STORY
    assert load_source(tmp_path, "s1", digest)["expanded_source"] == "I am a man."


def test_fonte_alterada_nao_sobrescreve_original(tmp_path):
    from utils.pipeline_recovery import save_source
    digest = source_sha256("Source", "I am a man.")
    path = save_source(tmp_path, STORY, digest, expanded_source="I am a man.")
    before = path.read_bytes()
    with pytest.raises(ValueError):
        save_source(tmp_path, STORY, "b" * 64, expanded_source="I am a woman.")
    assert path.read_bytes() == before


@pytest.mark.parametrize("story_id", ["../escape", "/absolute", "C:/outside", "a\\b"])
def test_fonte_caminho_invalido_nao_escreve(tmp_path, story_id):
    from utils.pipeline_recovery import save_source
    with pytest.raises(ValueError):
        save_source(tmp_path, {**STORY, "id": story_id}, "a" * 64, expanded_source=STORY["text"])
    assert list(tmp_path.iterdir()) == []


def test_checkpoint_exige_fonte_perfil_e_hash_integros(tmp_path):
    from utils.pipeline_recovery import save_approved_step, load_approved_step
    payload = {"source_sha256": "a" * 64, "profile_id": "p1", "text": "Texto aprovado.", "factual_context": "[]"}
    save_approved_step(tmp_path, "s1", "pt", "translation", payload)
    assert load_approved_step(tmp_path, "s1", "pt", "translation", "a" * 64, "p1") == payload
    assert load_approved_step(tmp_path, "s1", "pt", "translation", "b" * 64, "p1") is None
    assert load_approved_step(tmp_path, "s1", "pt", "translation", "a" * 64, "p2") is None
    path = next((tmp_path / "data/recovery").rglob("translation.json"))
    content = json.loads(path.read_text(encoding="utf-8"))
    content["payload"]["text"] = "Alterado."
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        load_approved_step(tmp_path, "s1", "pt", "translation", "a" * 64, "p1")


def test_organizer_falha_de_fila_nao_marca_exportado(tmp_path, monkeypatch):
    from scheduler import queue
    from stages.organizer import FileOrganizer
    from utils.db import PipelineDB
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [tmp_path / "data/queue"])
    db = PipelineDB(tmp_path / "db/pipeline.db")
    db.insert_story(STORY)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    meta = tmp_path / "meta.json"
    meta.write_text('{}', encoding="utf-8")
    def fail(*args, **kwargs):
        raise queue.QueueStateError("Fila indisponível")
    monkeypatch.setattr(queue, "enqueue_many", fail)
    with pytest.raises(queue.QueueStateError):
        FileOrganizer({"base_dir": str(tmp_path)}, db).organize_batch([
            dict(story_id="s1", language="pt", part=1, total=1, video_path=video,
                 thumbnail_path=None, metadata_path=meta, story_title="Título")], generation_key="a" * 64)
    assert db.get_pending("pt") == []


def test_batches_com_mesmo_titulo_nao_sobrescrevem_video(tmp_path, monkeypatch):
    from scheduler import queue
    from stages.organizer import FileOrganizer
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [tmp_path / "data/queue"])
    organizer = FileOrganizer({"base_dir": str(tmp_path)})
    paths = []
    for story_id, content, key in [("s1", b"first", "a" * 64), ("s2", b"second", "b" * 64)]:
        video = tmp_path / f"{story_id}.mp4"
        video.write_bytes(content)
        meta = tmp_path / f"{story_id}.json"
        meta.write_text('{}', encoding="utf-8")
        paths.append(organizer.organize_batch([
            dict(story_id=story_id, language="pt", part=1, total=1, video_path=video,
                 thumbnail_path=None, metadata_path=meta, story_title="Mesmo título")], generation_key=key)[0]["mp4"])
    assert Path(paths[0]).read_bytes() == b"first"
    assert Path(paths[1]).read_bytes() == b"second"
    assert paths[0] != paths[1]
