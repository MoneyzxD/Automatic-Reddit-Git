"""Snapshots privados íntegros e restauração entre raízes/runner."""
from dataclasses import replace
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tarfile

import pytest

from scheduler import queue
from stages.narrator_profile import NarratorProfileResolver, save_profile, source_sha256
from utils.db import PipelineDB
from utils.pipeline_recovery import save_source, save_approved_step


@pytest.fixture
def snapshot_fixture(tmp_path, monkeypatch):
    base = tmp_path / "original"
    db = PipelineDB(base / "db/pipeline.db")
    story = {"id": "s1", "title": "Source", "text": "I am a man."}
    digest = source_sha256(story["title"], story["text"])
    save_source(base, story, digest, expanded_source=story["text"])
    profile = NarratorProfileResolver({}, semantic_enabled=False).resolve(
        story_id="s1", title=story["title"], original_text=story["text"])
    save_profile(profile, base)
    save_approved_step(base, "s1", "pt", "translation", {
        "source_sha256": digest, "profile_id": profile.profile_id, "text": "Sou um homem."})
    db.register_story(story, ["pt"], digest)
    db.set_language_status("s1", "pt", "processing", profile_id=profile.profile_id)
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [base / "data/queue"])
    export = base / "data/exports/pt"
    export.mkdir(parents=True)
    (export / "a.mp4").write_bytes(b"video")
    (export / "a.jpg").write_bytes(b"image")
    (export / "a.json").write_text('{"title":"Source"}', encoding="utf-8")
    queue.enqueue_many("pt", [dict(video_path=export / "a.mp4", thumbnail_path=export / "a.jpg",
                                  metadata={"narrator_profile_id": profile.profile_id}, title="Source",
                                  story_id="s1", part=1, total=1)], generation_key="a" * 64)
    db.set_language_status("s1", "pt", "exported", profile_id=profile.profile_id)
    (base / ".env").write_text("KEY=SYNTHETIC", encoding="utf-8")
    (base / "secrets").mkdir()
    (base / "secrets/token.json").write_text('{"token":"SYNTHETIC"}', encoding="utf-8")
    (base / "data/logs").mkdir()
    (base / "data/logs/private.log").write_text("SYNTHETIC", encoding="utf-8")
    return base, db


def build(fixture, name="test-1"):
    from utils.pipeline_snapshot import build_snapshot
    base, db = fixture
    return build_snapshot(base, db.db_path, snapshot_id=name,
                          namespace="validation-test", run_id="1", commit="abc")


def repack(snapshot, *, extra=None, replacements=None):
    """Recalcula hashes: testes adversariais não param só no hash do TAR."""
    with tarfile.open(snapshot.payload_path, "r:gz") as archive:
        entries = [(member, archive.extractfile(member).read()) for member in archive.getmembers()]
    manifest = json.loads(json.dumps(snapshot.manifest))
    with tarfile.open(snapshot.payload_path, "w:gz") as archive:
        for member, data in entries:
            data = (replacements or {}).get(member.name, data)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
            manifest["files"][member.name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if extra:
            member, data = extra
            archive.addfile(member, io.BytesIO(data) if member.isreg() else None)
            manifest["files"][member.name] = {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    manifest["payload_sha256"] = hashlib.sha256(snapshot.payload_path.read_bytes()).hexdigest()
    return replace(snapshot, manifest=manifest)


def test_snapshot_restaura_fila_e_midia_em_outra_raiz(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import restore_snapshot
    snapshot = build(snapshot_fixture)
    destination = tmp_path / "restored"
    restore_snapshot(snapshot, destination)
    restore_snapshot(snapshot, destination)
    data = json.loads((destination / "data/queue/pt.json").read_text(encoding="utf-8"))
    video = Path(data["items"][0]["video_path"])
    assert video.is_relative_to(destination)
    assert video.read_bytes() == b"video"
    assert Path(data["items"][0]["thumbnail_path"]).read_bytes() == b"image"
    assert len(data["items"]) == 1
    assert not (destination / "secrets").exists()
    assert not (destination / ".env").exists()
    assert not (destination / "data/logs").exists()
    assert "SYNTHETIC" not in snapshot.payload_path.read_bytes().decode("latin1")
    ready = json.loads((destination / "data/state/ready.json").read_text(encoding="utf-8"))
    assert ready["namespace"] == "validation-test"
    assert ready["root"] == str(destination.resolve())
    assert not (destination / "data/state/restoring.json").exists()
    with sqlite3.connect(destination / "db/pipeline.db") as conn:
        assert conn.execute("PRAGMA quick_check").fetchall() == [("ok",)]
        assert conn.execute("SELECT status FROM story_languages").fetchone() == ("exported",)


def test_snapshot_apos_limpeza_preserva_id_sem_midia(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import restore_snapshot
    base, _ = snapshot_fixture
    item = queue.get_pending("pt")[0]
    queue.update_status("pt", item["id"], "youtube", "uploaded", video_id="vid1")
    queue.update_status("pt", item["id"], "tiktok", "uploaded", video_id="tt1")
    Path(item["video_path"]).unlink()
    Path(item["thumbnail_path"]).unlink()
    queue.mark_for_deletion("pt", item["id"])
    snapshot = build(snapshot_fixture)
    assert snapshot.media == {}
    destination = tmp_path / "restored"
    restore_snapshot(snapshot, destination)
    data = json.loads((destination / "data/queue/pt.json").read_text(encoding="utf-8"))
    assert data["items"][0]["platforms"]["youtube"]["video_id"] == "vid1"
    assert data["items"][0]["video_path"] is None


def test_thumbnail_falha_exige_midia_preservada(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    item = queue.get_pending("pt")[0]
    queue.update_status("pt", item["id"], "youtube", "uploaded", video_id="vid1", thumbnail={"status": "failed"})
    queue.update_status("pt", item["id"], "tiktok", "uploading")
    Path(item["video_path"]).unlink()
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


@pytest.mark.parametrize("corrupt", ["payload", "media"])
def test_hash_errado_nao_sobrescreve_destino(snapshot_fixture, tmp_path, corrupt):
    from utils.pipeline_snapshot import restore_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    path = snapshot.payload_path if corrupt == "payload" else next(iter(snapshot.media.values()))
    path.write_bytes(b"corrupt")
    target = tmp_path / "target"
    (target / "db").mkdir(parents=True)
    prior = target / "db/pipeline.db"
    prior.write_bytes(b"prior")
    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, target)
    assert prior.read_bytes() == b"prior"
    assert not (target / "data/state/ready.json").exists()


@pytest.mark.parametrize("operation", ["verify", "restore"])
def test_alias_de_midia_windows_rejeitado_antes_de_mutar(snapshot_fixture, tmp_path, operation):
    from utils.pipeline_snapshot import verify_snapshot, restore_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    with tarfile.open(snapshot.payload_path, "r:gz") as archive:
        data = json.loads(archive.extractfile("data/queue/pt.json").read())
    item = json.loads(json.dumps(data["items"][0]))
    item.update(id="alias_pt", video_path="data/exports/pt/A.mp4", thumbnail_path=None)
    item.pop("generation_key")
    data["items"].append(item)
    snapshot = repack(snapshot, replacements={"data/queue/pt.json": json.dumps(data).encode("utf-8")})
    digest = hashlib.sha256(b"video").hexdigest()
    snapshot.manifest["media"][digest]["paths"].append(item["video_path"])
    snapshot.manifest["queue_paths"]["data/queue/pt.json"][item["id"]] = {
        "video_path": item["video_path"], "thumbnail_path": None}
    target = tmp_path / "target"
    (target / "db").mkdir(parents=True)
    prior = target / "db/pipeline.db"
    prior.write_bytes(b"prior")
    with pytest.raises(SnapshotError):
        if operation == "verify":
            verify_snapshot(snapshot)
        else:
            restore_snapshot(snapshot, target)
    assert prior.read_bytes() == b"prior"
    assert not (target / "data/state/ready.json").exists()
    assert not (target / "data/state/restoring.json").exists()


@pytest.mark.parametrize("suffix", ["-wal", "-shm", "-journal"])
def test_sidecar_sqlite_residual_bloqueia_restore_antes_de_commit(snapshot_fixture, tmp_path, suffix):
    from utils.pipeline_snapshot import restore_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    target = tmp_path / "target"
    (target / "db").mkdir(parents=True)
    prior = target / "db/pipeline.db"
    prior.write_bytes(b"prior")
    sidecar = target / ("db/pipeline.db" + suffix)
    sidecar.write_bytes(b"residuo")
    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, target)
    assert prior.read_bytes() == b"prior"
    assert sidecar.read_bytes() == b"residuo"
    assert not (target / "data/state/ready.json").exists()


@pytest.mark.parametrize("language", ["pt", "pt-br", "en", "es"])
def test_fila_restaurada_ausente_nunca_vira_vazia(tmp_path, monkeypatch, language):
    from utils.pipeline_snapshot import build_snapshot, restore_snapshot, SnapshotError
    base = tmp_path / "legacy"
    database = PipelineDB(base / "db/pipeline.db")
    database.insert_story({"id": "legacy_story"})
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [base / "data/queue"])
    video = base / "data/exports/pt/legacy.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"video")
    queue.enqueue("pt", video, None, {}, "Title", story_id="legacy_story")
    snapshot = build_snapshot(base, database.db_path, snapshot_id="initial", namespace="production", run_id="1", commit="abc")
    target = tmp_path / "restored"
    restore_snapshot(snapshot, target)
    (target / f"data/queue/{language}.json").unlink()
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    with pytest.raises(SnapshotError):
        build_snapshot(target, target / "db/pipeline.db", snapshot_id="next", namespace="production", run_id="2", commit="abc")
    assert PipelineDB(target / "db/pipeline.db").story_exists("legacy_story")


@pytest.mark.parametrize("name,kind", [
    ("../escape", "file"), ("/absolute", "file"), ("C:/outside", "file"),
    ("data\\..\\escape", "file"), ("data//x", "file"), ("data/./x", "file"),
    ("data/link", "symlink"), ("data/link", "hardlink"),
    ("db/pipeline.db", "duplicate"), ("secrets/token.json", "file"),
])
def test_tar_adversarial_mesmo_com_hash_valido_bloqueia(snapshot_fixture, tmp_path, name, kind):
    from utils.pipeline_snapshot import restore_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    member = tarfile.TarInfo(name)
    member.size = 1 if kind in {"file", "duplicate"} else 0
    if kind in {"symlink", "hardlink"}:
        member.type = tarfile.SYMTYPE if kind == "symlink" else tarfile.LNKTYPE
        member.linkname = "../escape"
    snapshot = repack(snapshot, extra=(member, b"x" if member.isreg() else b""))
    target = tmp_path / "target"
    with pytest.raises(SnapshotError):
        restore_snapshot(snapshot, target)
    assert not (tmp_path / "escape").exists()
    assert not (target / "db/pipeline.db").exists()


def test_fila_pendente_sem_mp4_bloqueia_build(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    (base / "data/exports/pt/a.mp4").unlink()
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_perfil_incompativel_bloqueia_build(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    path = next((base / "data/scripts/profiles").glob("*.json"))
    content = json.loads(path.read_text(encoding="utf-8"))
    content["profile_id"] = "wrong"
    path.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_hardlink_na_origem_nao_e_copiado(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    file = base / "data/exports/pt/a.mp4"
    file.unlink()
    os.link(base / ".env", file)
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_source_gerenciada_ausente_bloqueia(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    (base / "data/recovery/s1/source.json").unlink()
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_idioma_exportado_sem_fila_nao_vira_snapshot_vazio(snapshot_fixture):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    (base / "data/queue/pt.json").unlink()
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_fila_com_referencia_externa_bloqueia(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import SnapshotError
    base, _ = snapshot_fixture
    path = base / "data/queue/pt.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    external = tmp_path / "external.mp4"
    external.write_bytes(b"outside")
    data["items"][0]["video_path"] = str(external)
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_db_corrompido_com_hash_atualizado_bloqueia(snapshot_fixture):
    from utils.pipeline_snapshot import verify_snapshot, SnapshotError
    snapshot = repack(build(snapshot_fixture), replacements={"db/pipeline.db": b"invalid sqlite"})
    with pytest.raises(SnapshotError):
        verify_snapshot(snapshot)


def test_queue_mapping_alterado_bloqueia(snapshot_fixture):
    from utils.pipeline_snapshot import verify_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    with tarfile.open(snapshot.payload_path, "r:gz") as archive:
        data = json.load(archive.extractfile("data/queue/pt.json"))
    data["items"][0]["video_path"] = "data/exports/pt/not-listed.mp4"
    snapshot = repack(snapshot, replacements={"data/queue/pt.json": json.dumps(data).encode()})
    with pytest.raises(SnapshotError):
        verify_snapshot(snapshot)


@pytest.mark.parametrize("limit", ["control", "media"])
def test_limite_configurado_bloqueia_sem_truncar(snapshot_fixture, monkeypatch, limit):
    from utils.pipeline_snapshot import verify_snapshot, SnapshotError
    snapshot = build(snapshot_fixture)
    monkeypatch.setenv(f"PIPELINE_STATE_{limit.upper()}_MAX_BYTES", "1")
    with pytest.raises(SnapshotError):
        verify_snapshot(snapshot)


@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "invalid"])
def test_limite_invalido_nao_libera_build(snapshot_fixture, monkeypatch, value):
    from utils.pipeline_snapshot import SnapshotError
    monkeypatch.setenv("PIPELINE_STATE_CONTROL_MAX_BYTES", value)
    with pytest.raises(SnapshotError):
        build(snapshot_fixture)


def test_limites_opcionais_vazios_usam_defaults(snapshot_fixture, monkeypatch):
    monkeypatch.setenv("PIPELINE_STATE_CONTROL_MAX_BYTES", "")
    monkeypatch.setenv("PIPELINE_STATE_MEDIA_MAX_BYTES", "")
    assert build(snapshot_fixture).media


def test_falha_no_commit_de_restauracao_deixa_marker_e_preimagem(snapshot_fixture, tmp_path, monkeypatch):
    from utils import pipeline_snapshot as module
    snapshot = build(snapshot_fixture)
    target = tmp_path / "target"
    (target / "db").mkdir(parents=True)
    (target / "db/pipeline.db").write_bytes(b"prior")
    original_replace = module.os.replace
    def fail(src, dst):
        if Path(dst) == target / "db/pipeline.db":
            raise OSError("synthetic")
        return original_replace(src, dst)
    monkeypatch.setattr(module.os, "replace", fail)
    with pytest.raises(module.SnapshotError):
        module.restore_snapshot(snapshot, target)
    assert (target / "data/state/restoring.json").exists()
    assert not (target / "data/state/ready.json").exists()
    assert any(path.read_bytes() == b"prior" for path in (target / "data/state").rglob("pipeline.db"))
