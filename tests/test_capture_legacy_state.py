"""Candidato legado privado não é head nem reconciliação aprovada."""
from contextlib import closing
import hashlib
import json
import sqlite3
import zipfile

import pytest

from scripts import capture_legacy_state
from utils.pipeline_state import StateError


def test_capture_preserva_db_e_fila_sem_incluir_credenciais(tmp_path):
    (tmp_path / "db").mkdir()
    db = tmp_path / "db/pipeline.db"
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("CREATE TABLE stories (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO stories VALUES ('sent-story')")
    queue = tmp_path / "data/queue"
    queue.mkdir(parents=True)
    original = b'{"language":"pt","items":[{"id":"sent","platforms":{"youtube":{"status":"uploaded","video_id":"abcdefghijk"}}}]}'
    (queue / "pt.json").write_bytes(original)
    (tmp_path / ".env").write_text("SECRET=not-exported")
    (queue / "youtube_token.json").write_text("secret")
    path = capture_legacy_state.build_candidate(tmp_path, "37209564422", "37240000000")
    with zipfile.ZipFile(path) as archive:
        assert set(archive.namelist()) == {"db/pipeline.db", "data/queue/pt.json", "candidate.json"}
        assert archive.read("data/queue/pt.json") == original
        manifest = json.loads(archive.read("candidate.json"))
        assert manifest["authoritative"] is False
        assert manifest["cache_run_id"] == "37209564422"
        assert manifest["files"]["data/queue/pt.json"] == hashlib.sha256(original).hexdigest()
        assert set(manifest["missing_queues"]) == {"en", "es", "pt-br"}
    assert (queue / "pt.json").read_bytes() == original
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT id FROM stories").fetchall() == [("sent-story",)]
    assert not (tmp_path / "data/state/ready.json").exists()


@pytest.mark.parametrize("cache_id,run_id", [("../1", "123"), ("123", "$(env)"), ("", "123")])
def test_capture_rejeita_identidade_invalida(tmp_path, cache_id, run_id):
    with pytest.raises(StateError):
        capture_legacy_state.build_candidate(tmp_path, cache_id, run_id)
    assert not (tmp_path / "data/state").exists()


def test_capture_nao_trata_db_ausente_como_vazio(tmp_path):
    with pytest.raises(StateError):
        capture_legacy_state.build_candidate(tmp_path, "123", "456")


def test_cli_candidato_corrompido_bloqueia_sem_gravar_release(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for name, value in {"LEGACY_CACHE_RUN_ID": "123", "MATCHED_DB_CACHE_KEY": "pipeline-db-123",
                        "MATCHED_QUEUE_CACHE_KEY": "pipeline-queue-123", "GITHUB_RUN_ID": "456"}.items():
        monkeypatch.setenv(name, value)
    (tmp_path / "db").mkdir()
    (tmp_path / "db/pipeline.db").write_bytes(b"broken-private-data")
    class Store:
        namespace = "legacy-inventory"
        def validate_target(self):
            pass
        def _ensure_release(self, *args):
            pytest.fail("Não deve escrever remoto com banco inválido")
    monkeypatch.setattr(capture_legacy_state.PrivateStateStore, "from_environment", lambda base: Store())
    assert capture_legacy_state.main() == 2
    assert "broken-private-data" not in capsys.readouterr().out


def test_cli_caches_divergentes_nao_abre_storage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("LEGACY_CACHE_RUN_ID", "123")
    monkeypatch.setenv("MATCHED_DB_CACHE_KEY", "pipeline-db-123")
    monkeypatch.setenv("MATCHED_QUEUE_CACHE_KEY", "pipeline-queue-122")
    def forbidden(base):
        pytest.fail("Candidato divergente não deve acessar storage")
    monkeypatch.setattr(capture_legacy_state.PrivateStateStore, "from_environment", forbidden)
    assert capture_legacy_state.main() == 2
