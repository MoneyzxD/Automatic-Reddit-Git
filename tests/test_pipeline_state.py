"""Transporte privado sem rede real, segredos ou publicação YouTube."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest
import requests

from test_pipeline_snapshot import snapshot_fixture, build

REPO = "MoneyzxD/Automatic-Reddit-State"


class Response:
    def __init__(self, status=200, data=None, *, content=b"", headers=None):
        self.status_code, self.data, self.content = status, data, content
        self.headers = headers or {}
    def json(self):
        if self.data is None:
            raise ValueError("synthetic")
        return self.data
    def iter_content(self, chunk_size=1024):
        yield self.content
    def close(self):
        pass


class Session:
    """API mínima em memória; IDs/bytes têm as mesmas relações do GitHub."""
    def __init__(self):
        self.calls, self.releases, self.assets = [], [], {}
        self.headers, self.auth, self.trust_env = {}, None, True
        self.repo = {"full_name": REPO, "private": True, "default_branch": "main"}
        self.repo_status = 200
        self.fail_marker = False
        self.page_size = 100
        self.redirect = None
        self.redirect_asset = None
    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        parsed = urlparse(url)
        prefix = f"/repos/{REPO}"
        path = parsed.path
        if parsed.hostname in {"release-assets.githubusercontent.com", "evil.test"}:
            return Response(content=self.assets[self.redirect_asset]["bytes"])
        if path == prefix:
            return Response(self.repo_status, self.repo)
        if method == "POST" and path == prefix + "/releases":
            release = {"id": len(self.releases) + 10, "tag_name": kwargs["json"]["tag_name"]}
            self.releases.append(release)
            return Response(201, release)
        if path.startswith(prefix + "/releases/tags/"):
            tag = path.rsplit("/", 1)[1]
            found = next((entry for entry in self.releases if entry["tag_name"] == tag), None)
            return Response(200 if found else 404, found)
        if path == prefix + "/releases":
            page = kwargs.get("params", {}).get("page", 1)
            start = (page - 1) * self.page_size
            return Response(data=list(reversed(self.releases))[start:start + self.page_size])
        if path.endswith("/assets") and "/releases/" in path:
            release_id = int(path.split("/releases/")[1].split("/")[0])
            if method == "POST":
                name = kwargs["params"]["name"]
                if self.fail_marker and name.startswith("complete-"):
                    raise requests.ConnectionError("SYNTHETIC_TOKEN signed-url")
                data = kwargs["data"]
                data = data.read() if hasattr(data, "read") else data
                asset_id = len(self.assets) + 100
                info = {"id": asset_id, "name": name, "size": len(data), "state": "uploaded",
                        "digest": "sha256:" + hashlib.sha256(data).hexdigest()}
                self.assets[asset_id] = {"info": info, "bytes": data, "release_id": release_id}
                return Response(201, info)
            page = kwargs.get("params", {}).get("page", 1)
            entries = [entry["info"] for entry in self.assets.values() if entry["release_id"] == release_id]
            start = (page - 1) * self.page_size
            return Response(data=entries[start:start + self.page_size])
        if path.startswith(prefix + "/releases/assets/"):
            asset_id = int(path.rsplit("/", 1)[1])
            if asset_id not in self.assets:
                return Response(404)
            if kwargs["headers"].get("Accept") == "application/octet-stream":
                if self.redirect:
                    self.redirect_asset = asset_id
                    return Response(302, headers={"Location": self.redirect})
                return Response(content=self.assets[asset_id]["bytes"])
            return Response(data=self.assets[asset_id]["info"])
        raise AssertionError(f"Rota de teste não implementada: {method} {path}")


def store(session=None, namespace="validation-test"):
    from utils.pipeline_state import PrivateStateStore
    return PrivateStateStore(REPO, "SYNTHETIC_TOKEN", namespace, session=session or Session())


@pytest.mark.parametrize("private,name", [(False, REPO), (True, "MoneyzxD/Other"), ("true", REPO)])
def test_destino_publico_ou_diferente_bloqueia_escrita(private, name):
    from utils.pipeline_state import StateError
    session = Session()
    session.repo.update(private=private, full_name=name)
    with pytest.raises(StateError):
        store(session).validate_target()
    assert all(method == "GET" for method, _, _ in session.calls)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500])
def test_erro_repo_nao_vira_estado_vazio_e_nao_vaza(status):
    from utils.pipeline_state import StateError
    session = Session()
    session.repo_status = status
    with pytest.raises(StateError) as caught:
        store(session).fetch_latest()
    assert "SYNTHETIC" not in str(caught.value)
    assert all(method == "GET" for method, _, _ in session.calls)


@pytest.mark.parametrize("namespace", ["../x", "", "bad space", "a/b"])
def test_namespace_invalido_bloqueia(namespace):
    from utils.pipeline_state import StateError
    with pytest.raises(StateError):
        store(namespace=namespace)


def test_token_publico_nao_substitui_secret_limitado(monkeypatch, tmp_path):
    from utils.pipeline_state import PrivateStateStore, StateError
    monkeypatch.delenv("PIPELINE_STATE_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "SYNTHETIC")
    monkeypatch.setenv("GH_TOKEN", "SYNTHETIC")
    monkeypatch.setenv("PIPELINE_STATE_REPO", REPO)
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "production")
    with pytest.raises(StateError):
        PrivateStateStore.from_environment(tmp_path)


def test_publish_marker_ultimo_replay_e_round_trip(snapshot_fixture, tmp_path):
    from utils.pipeline_snapshot import restore_snapshot
    session = Session()
    client = store(session)
    snapshot = build(snapshot_fixture)
    receipt = client.publish(snapshot)
    assert receipt["snapshot_id"] == snapshot.snapshot_id
    posts = [kwargs for method, url, kwargs in session.calls if method == "POST" and urlparse(url).hostname == "uploads.github.com"]
    assert posts[-1]["params"]["name"] == "complete-0.json"
    assert posts[0]["params"]["name"].startswith("media-")
    prior = len(session.assets)
    assert client.publish(snapshot) == receipt
    assert len(session.assets) == prior
    latest = client.fetch_latest()
    restore_snapshot(latest, tmp_path / "restored")
    data = json.loads((tmp_path / "restored/data/queue/pt.json").read_text(encoding="utf-8"))
    assert Path(data["items"][0]["video_path"]).read_bytes() == b"video"
    assert not any(method == "DELETE" for method, _, _ in session.calls)


def test_falha_no_marker_conserva_head_anterior(snapshot_fixture):
    from utils.pipeline_state import StateError
    session = Session()
    client = store(session)
    first = build(snapshot_fixture)
    client.publish(first)
    second = replace(first, snapshot_id="test-2", manifest={**first.manifest, "snapshot_id": "test-2", "sequence": 1})
    session.fail_marker = True
    with pytest.raises(StateError) as caught:
        client.publish(second)
    assert "SYNTHETIC" not in str(caught.value)
    assert client.fetch_latest().snapshot_id == first.snapshot_id


def test_ultimo_completo_corrompido_nao_volta_ao_anterior(snapshot_fixture):
    from utils.pipeline_state import StateError
    session = Session()
    client = store(session)
    first = build(snapshot_fixture)
    client.publish(first)
    second = replace(first, snapshot_id="test-2", manifest={**first.manifest, "snapshot_id": "test-2", "sequence": 1})
    receipt = client.publish(second)
    session.assets[receipt["payload_id"]]["bytes"] = b"corrupt"
    with pytest.raises(StateError):
        client.fetch_latest()


def test_paginacao_completa_e_retencao_sem_delete(snapshot_fixture):
    session = Session()
    session.page_size = 1
    client = store(session)
    first = build(snapshot_fixture)
    for run_id in range(1, 5):
        snapshot = replace(first, snapshot_id=f"test-{run_id}", manifest={
            **first.manifest, "snapshot_id": f"test-{run_id}", "run_id": str(run_id)})
        client.publish(snapshot)
    assert client.fetch_latest().snapshot_id == "test-4"
    assert len([entry for entry in session.assets.values() if entry["info"]["name"].startswith("complete-")]) == 4
    assert any(kwargs.get("params", {}).get("page", 0) > 1 for _, _, kwargs in session.calls)
    assert not any(method == "DELETE" for method, _, _ in session.calls)


def test_download_redirecionado_remove_auth_e_verifica_tls(snapshot_fixture):
    session = Session()
    client = store(session)
    client.publish(build(snapshot_fixture))
    session.redirect = "https://release-assets.githubusercontent.com/private?signature=SYNTHETIC"
    client.fetch_latest()
    redirected = [kwargs for _, url, kwargs in session.calls if urlparse(url).hostname == "release-assets.githubusercontent.com"]
    assert redirected
    assert all("Authorization" not in kwargs["headers"] for kwargs in redirected)
    assert all(kwargs["verify"] is True and kwargs["allow_redirects"] is False for _, _, kwargs in session.calls)
    assert session.trust_env is False


@pytest.mark.parametrize("url", ["https://evil.test/private", "http://release-assets.githubusercontent.com/private",
                                 "https://api.github.com@evil.test/private"])
def test_redirect_inseguro_bloqueia_sem_enviar_token(snapshot_fixture, url):
    from utils.pipeline_state import StateError
    session = Session()
    client = store(session)
    client.publish(build(snapshot_fixture))
    session.redirect = url
    with pytest.raises(StateError):
        client.fetch_latest()
    assert not any(urlparse(target).hostname == "evil.test" for _, target, _ in session.calls)


def test_save_exige_ready_e_sequencia_persistida(snapshot_fixture, monkeypatch):
    from utils import pipeline_state as module
    from utils.pipeline_snapshot import restore_snapshot
    base, db = snapshot_fixture
    client = store()
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setenv("PIPELINE_DB_PATH", str(db.db_path))
    monkeypatch.setenv("GITHUB_RUN_ID", "10")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", "abc")
    monkeypatch.setattr(module.PrivateStateStore, "from_environment", lambda root: client)
    with pytest.raises(module.StateError):
        module.checkpoint_from_environment(base, reason="test")
    restore_snapshot(build(snapshot_fixture), base)
    first = module.checkpoint_from_environment(base, reason="source")
    second = module.checkpoint_from_environment(base, reason="export")
    assert second["manifest"]["sequence"] == first["manifest"]["sequence"] + 1


@pytest.mark.parametrize("run_id,attempt", [("9", "1"), ("10", "1")])
def test_run_anterior_ao_head_nao_confirma_checkpoint(snapshot_fixture, monkeypatch, run_id, attempt):
    from utils import pipeline_state as module
    from utils.pipeline_snapshot import restore_snapshot
    base, db = snapshot_fixture
    first = build(snapshot_fixture)
    first = replace(first, manifest={**first.manifest, "run_id": "10", "run_attempt": 2})
    restore_snapshot(first, base)
    client = store()
    monkeypatch.setenv("PIPELINE_DB_PATH", str(db.db_path))
    monkeypatch.setenv("GITHUB_RUN_ID", run_id)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", attempt)
    monkeypatch.setenv("GITHUB_SHA", "abc")
    monkeypatch.setattr(module.PrivateStateStore, "from_environment", lambda root: client)
    with pytest.raises(module.StateError):
        module.checkpoint_from_environment(base, reason="before_upload")
    assert not any(method == "POST" for method, _, _ in client.session.calls)
    assert not (base / "data/state/sequence.json").exists()


def test_snapshot_error_vira_state_error_seguro(snapshot_fixture, monkeypatch):
    from utils import pipeline_state as module
    from utils.pipeline_snapshot import restore_snapshot, SnapshotError
    base, _ = snapshot_fixture
    restore_snapshot(build(snapshot_fixture), base)
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setenv("GITHUB_RUN_ID", "10")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setattr(module.PrivateStateStore, "from_environment", lambda root: store())
    def fail(*args, **kwargs):
        raise SnapshotError("SYNTHETIC_TOKEN")
    monkeypatch.setattr(module, "build_snapshot", fail)
    with pytest.raises(module.StateError) as caught:
        module.checkpoint_from_environment(base, reason="test")
    assert "SYNTHETIC" not in str(caught.value)


def test_bootstrap_vazio_obrigatorio_cria_filas_explicitas(tmp_path, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    client = store(namespace="validation-new")
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    assert main(["bootstrap", "--base-dir", str(tmp_path), "--namespace", "validation-new", "--allow-empty-validation"]) == 0
    for language in ("pt", "pt-br", "en", "es"):
        data = json.loads((tmp_path / f"data/queue/{language}.json").read_text(encoding="utf-8"))
        assert data["items"] == []


def test_cli_bootstrap_vazio_so_validacao(tmp_path, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    client = store(namespace="production")
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    assert main(["bootstrap", "--base-dir", str(tmp_path), "--namespace", "production", "--allow-empty-validation"]) != 0
    assert not (tmp_path / "db/pipeline.db").exists()


def test_cli_bootstrap_validacao_nao_sobrescreve_head(snapshot_fixture, tmp_path, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    client = store()
    client.publish(build(snapshot_fixture))
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    assert main(["bootstrap", "--base-dir", str(tmp_path), "--namespace", "validation-test", "--allow-empty-validation"]) == 0
    data = json.loads((tmp_path / "data/queue/pt.json").read_text(encoding="utf-8"))
    assert len(data["items"]) == 1


def test_cli_bootstrap_vazio_exige_listagem_autorizada(tmp_path, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    session = Session()
    session.repo_status = 403
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: store(session))
    assert main(["bootstrap", "--base-dir", str(tmp_path), "--namespace", "validation-test", "--allow-empty-validation"]) != 0
    assert not (tmp_path / "db/pipeline.db").exists()


def test_cli_bootstrap_novo_vazio_valida_e_publica(tmp_path, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    client = store()
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    assert main(["bootstrap", "--base-dir", str(tmp_path), "--namespace", "validation-test", "--allow-empty-validation"]) == 0
    assert (tmp_path / "data/state/ready.json").exists()
    assert all(json.loads((tmp_path / f"data/queue/{lang}.json").read_text())["items"] == []
               for lang in ("pt", "pt-br", "en", "es"))
    assert client.fetch_latest().namespace == "validation-test"


def test_cli_relatorio_privado_e_bootstrap_com_digest(snapshot_fixture, monkeypatch):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    base, _ = snapshot_fixture
    report = base / "data/state/reconciliation.json"
    assert main(["verify", "--base-dir", str(base), "--namespace", "validation-test", "--legacy-report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["inventory"]["db/pipeline.db"]
    assert ".env" not in data["inventory"]
    client = store()
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    assert main(["bootstrap", "--base-dir", str(base), "--namespace", "validation-test",
                 "--reconciliation-file", str(report), "--confirm-digest", hashlib.sha256(report.read_bytes()).hexdigest()]) == 0
    assert client.fetch_latest().manifest["queue_paths"]["data/queue/pt.json"]


@pytest.mark.parametrize("change", ["digest", "queue"])
def test_cli_bootstrap_invalida_aprovacao_se_dados_mudaram(snapshot_fixture, monkeypatch, change):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    base, _ = snapshot_fixture
    report = base / "data/state/reconciliation.json"
    assert main(["verify", "--base-dir", str(base), "--namespace", "validation-test", "--legacy-report", str(report)]) == 0
    digest = hashlib.sha256(report.read_bytes()).hexdigest()
    if change == "digest":
        digest = "a" * 64
    else:
        path = base / "data/queue/pt.json"
        path.write_bytes(path.read_bytes() + b" ")
    session = Session()
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: store(session))
    assert main(["bootstrap", "--base-dir", str(base), "--namespace", "validation-test",
                 "--reconciliation-file", str(report), "--confirm-digest", digest]) != 0
    assert not any(method == "POST" for method, _, _ in session.calls)
    assert not (base / "data/state/ready.json").exists()


def test_cli_relatorio_nao_pode_ser_gravado_no_repo_publico(snapshot_fixture):
    from scripts.pipeline_state import main
    base, _ = snapshot_fixture
    path = base / "report.json"
    assert main(["verify", "--base-dir", str(base), "--namespace", "validation-test", "--legacy-report", str(path)]) != 0
    assert not path.exists()


def test_ready_de_outra_raiz_nao_autoriza_checkpoint(snapshot_fixture, monkeypatch):
    from utils import pipeline_state as module
    from utils.pipeline_snapshot import restore_snapshot
    base, _ = snapshot_fixture
    restore_snapshot(build(snapshot_fixture), base)
    ready = base / "data/state/ready.json"
    data = json.loads(ready.read_text(encoding="utf-8"))
    data["root"] = "other"
    ready.write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setattr(module.PrivateStateStore, "from_environment", lambda root: store())
    with pytest.raises(module.StateError):
        module.checkpoint_from_environment(base, reason="test")
    assert not (base / "data/state/sequence.json").exists()


@pytest.mark.parametrize("decision", [None, "retain_pending", "confirmed_uploaded", "cancel_unknown"])
def test_bootstrap_legado_exige_decisao_e_preserva_dedupe(tmp_path, monkeypatch, decision):
    from scripts.pipeline_state import main
    from utils.pipeline_state import PrivateStateStore
    from utils.db import PipelineDB
    from scheduler import queue
    base = tmp_path / "base"
    database = PipelineDB(base / "db/pipeline.db")
    database.insert_story({"id": "legacy"})
    media = base / "data/exports/pt/old.mp4"
    media.parent.mkdir(parents=True)
    media.write_bytes(b"video")
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [base / "data/queue"])
    item_id = queue.enqueue("pt", media, None, {}, "Old", story_id="legacy")
    report = base / "data/state/reconciliation.json"
    assert main(["verify", "--base-dir", str(base), "--namespace", "validation-test", "--legacy-report", str(report)]) == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    if decision:
        data["decisions"] = [{"language": "pt", "item_id": item_id, "action": decision,
                              "studio_checked": True, "confirmed_absent": True,
                              "video_id": "abcdefghijk", "confirmed_at": "2026-10-03T12:00:00+00:00"}]
        report.write_text(json.dumps(data), encoding="utf-8")
    session = Session()
    client = store(session)
    monkeypatch.setattr(PrivateStateStore, "from_environment", lambda root: client)
    code = main(["bootstrap", "--base-dir", str(base), "--namespace", "validation-test",
                 "--reconciliation-file", str(report), "--confirm-digest", hashlib.sha256(report.read_bytes()).hexdigest()])
    if not decision:
        assert code != 0
        assert not any(method == "POST" for method, _, _ in session.calls)
        assert queue.get_pending("pt")[0]["id"] == item_id
    else:
        assert code == 0
        item = queue._load_queue("pt")["items"][0]
        expected = {"retain_pending": "pending", "confirmed_uploaded": "uploaded", "cancel_unknown": "cancelled"}
        assert item["platforms"]["youtube"]["status"] == expected[decision]
        if decision == "confirmed_uploaded":
            assert item["platforms"]["youtube"]["video_id"] == "abcdefghijk"
        assert database.processing_languages("legacy", ["pt", "en", "es"]) == []


def test_marker_corrompido_nao_vira_namespace_novo(snapshot_fixture):
    from utils.pipeline_state import StateError
    session = Session()
    client = store(session)
    client.publish(build(snapshot_fixture))
    marker = next(entry for entry in session.assets.values() if entry["info"]["name"].startswith("complete-"))
    marker["bytes"] = b"{broken"
    marker["info"].update(size=len(marker["bytes"]), digest="sha256:" + hashlib.sha256(marker["bytes"]).hexdigest())
    with pytest.raises(StateError):
        client.fetch_latest()
