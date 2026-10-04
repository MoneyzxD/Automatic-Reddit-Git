"""Contrato de execução isolada; YAML não substitui validação real do Actions."""
from pathlib import Path
import json
from unittest.mock import Mock
from contextlib import closing
import sqlite3

import pytest
import yaml

import main
from utils.pipeline_state import StateError
from test_pipeline_quality_gate import pipeline


BASE = Path(__file__).resolve().parent.parent


def workflow():
    return yaml.load((BASE / ".github/workflows/pipeline.yml").read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def test_workflow_restauracao_antecede_geracao_e_publicacao():
    data = workflow()
    assert set(data["on"]["workflow_dispatch"]["inputs"]["state_action"]["options"]) == {"normal", "bootstrap", "verify"}
    steps = data["jobs"]["gerar-e-publicar"]["steps"]
    ids = [step.get("id") for step in steps]
    assert ids.index("state_restore") < ids.index("generate") < ids.index("publish")
    for name in ("generate", "publish"):
        step = steps[ids.index(name)]
        assert "steps.execution.outputs." in step["if"]
        assert "secrets.PIPELINE_STATE_TOKEN" in step["env"]["PIPELINE_STATE_TOKEN"]
    final = steps[ids.index("state_save")]
    assert "always()" in final["if"] and "steps.state_restore.outcome == 'success'" in final["if"]
    assert "save-if-ready" in final["run"]


def test_workflow_isola_namespace_cache_secrets_e_artifacts():
    data = workflow()
    assert "pipeline-videos" in data["concurrency"]["group"]
    assert "validation_namespace" in data["concurrency"]["group"]
    job = data["jobs"]["gerar-e-publicar"]
    assert "PIPELINE_STATE_TOKEN" not in job["env"]
    steps = job["steps"]
    resolution = next(step for step in steps if step.get("id") == "execution")
    assert "inputs.validation_namespace" in resolution["env"]["INPUT_VALIDATION_NAMESPACE"]
    assert "${{" not in resolution["run"]
    for step in steps:
        if step.get("run") == "python -m pytest tests -q":
            assert "PIPELINE_STATE_TOKEN" not in step.get("env", {})
            assert "PIPELINE_STATE_REQUIRED" not in step.get("env", {})
        if step.get("uses", "").startswith("actions/cache/restore"):
            assert "bootstrap" in step.get("if", "")
        if step.get("uses", "").startswith("actions/upload-artifact"):
            paths = step["with"]["path"]
            assert not any(value in paths for value in ("data/state", "data/recovery", "db/", "data/queue", "data/scripts/profiles"))


def test_perfis_de_recuperacao_ficam_fora_do_git_publico():
    assert "data/scripts/profiles/" in (BASE / ".gitignore").read_text(encoding="utf-8").splitlines()


@pytest.mark.parametrize("options,expected", [
    ({}, ("production", True, True, "restore")),
    ({"only_generate": True}, ("validation-123", True, False, "bootstrap-validation")),
    ({"test_story": True}, ("validation-123", True, False, "bootstrap-validation")),
    ({"dry_run": True}, ("validation-123", True, False, "skip")),
    ({"state_action": "verify", "validation_namespace": "validation-shared"}, ("validation-shared", False, False, "restore")),
    ({"state_action": "bootstrap"}, ("production", False, False, "bootstrap")),
])
def test_resolucao_de_modo(options, expected):
    from utils.pipeline_execution import resolve_execution
    result = resolve_execution(event="workflow_dispatch", ref="refs/heads/main", run_id="123", **options)
    assert (result["namespace"], result["generate"], result["publish"], result["state_operation"]) == expected


@pytest.mark.parametrize("options", [
    {"validation_namespace": "production"}, {"validation_namespace": "validation-../../secret"},
    {"validation_namespace": "validation-$(env)"}, {"ref": "refs/heads/feature"},
    {"state_action": "invalid"}, {"event": "pull_request"}, {"run_id": "$(env)"},
    {"validation_namespace": "validation-ok"},
])
def test_resolucao_rejeita_entrada_insegura(options):
    from utils.pipeline_execution import resolve_execution
    values = dict(event="workflow_dispatch", ref="refs/heads/main", run_id="123")
    values.update(options)
    with pytest.raises(StateError):
        resolve_execution(**values)


def test_cron_somente_main_production():
    from utils.pipeline_execution import resolve_execution
    result = resolve_execution(event="schedule", ref="refs/heads/main", run_id="123", only_generate=True, test_story=True)
    assert result["publish"] is True and result["namespace"] == "production"
    with pytest.raises(StateError):
        resolve_execution(event="schedule", ref="refs/heads/feature", run_id="123")


def test_pipeline_sem_recibo_bloqueia_antes_de_extracao(pipeline, monkeypatch):
    from stages import extractor
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "production")
    spy = Mock()
    monkeypatch.setattr(extractor, "RedditExtractor", spy)
    with pytest.raises(StateError):
        main.run_pipeline(pipeline.config, ["pt"])
    spy.assert_not_called()
    assert pipeline.audios == []


def test_pipeline_checkpoint_falho_interrompe_antes_da_voz(pipeline, monkeypatch):
    from utils import pipeline_state
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setattr(pipeline_state, "require_ready", lambda *args: {})
    seen = []
    def save(base, *, reason):
        seen.append(reason)
        if reason == "parts_prepared":
            raise StateError("Falha sintética")
        return {}
    monkeypatch.setattr(pipeline_state, "checkpoint_from_environment", save)
    with pytest.raises(StateError):
        main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert seen == ["source_registered", "narrator_locked", "adaptation_approved", "localized_script_approved", "parts_prepared"]
    assert pipeline.audios == []
    with closing(sqlite3.connect(pipeline.root / "db/pipeline.db")) as connection:
        assert connection.execute("SELECT status FROM story_languages WHERE story_id='s1' AND language='pt'").fetchone() == ("processing",)


def test_checkpoint_de_exportacao_recebe_idioma_completo(pipeline, monkeypatch):
    from utils import pipeline_state
    from scheduler import queue
    # A fixture imita o restore completo, incluindo as filas explícitas vazias.
    for language in ("pt", "pt-br", "en", "es"):
        queue._save_queue(language, {"language": language, "items": [], "uploads_today": 0, "last_upload_at": None})
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setattr(pipeline_state, "require_ready", lambda *args: {})
    seen = []
    def save(base, *, reason):
        seen.append(reason)
        if reason == "language_exported":
            data = json.loads((base / "data/queue/pt.json").read_text(encoding="utf-8"))
            assert data["items"] and all(Path(item["video_path"]).is_file() for item in data["items"])
        return {}
    monkeypatch.setattr(pipeline_state, "checkpoint_from_environment", save)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert seen[-1] == "language_exported"


def test_cli_state_error_retorna_codigo_2(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "BASE_DIR", tmp_path)
    monkeypatch.setattr(main, "load_config", lambda: {})
    monkeypatch.setattr(main, "run_pipeline", Mock(side_effect=StateError("Falha sintética")))
    assert main.cli(["--lang", "pt"]) == 2


def test_save_final_sem_recibo_nao_cria_storage(monkeypatch, tmp_path):
    from scripts import pipeline_state
    spy = Mock()
    monkeypatch.setattr(pipeline_state.PrivateStateStore, "from_environment", spy)
    assert pipeline_state.main(["save-if-ready", "--base-dir", str(tmp_path), "--namespace", "production"]) == 0
    spy.assert_not_called()


def test_save_final_com_restauracao_incompleta_nao_grava(monkeypatch, tmp_path):
    from scripts import pipeline_state
    directory = tmp_path / "data/state"
    directory.mkdir(parents=True)
    (directory / "restoring.json").write_text("{}", encoding="utf-8")
    spy = Mock()
    monkeypatch.setattr(pipeline_state, "checkpoint_from_environment", spy)
    assert pipeline_state.main(["save-if-ready", "--base-dir", str(tmp_path), "--namespace", "production"]) == 0
    spy.assert_not_called()


def test_resolver_idiomas_livres_nao_escreve_output(monkeypatch, tmp_path):
    from utils import pipeline_execution
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "output"))
    monkeypatch.setenv("INPUT_LANGUAGES", "pt --test-story")
    assert pipeline_execution.main() == 2
    assert not (tmp_path / "output").exists()


def test_checkpoints_main_sao_snapshots_verificaveis(pipeline, monkeypatch):
    from utils import pipeline_state
    from utils.db import PipelineDB
    from utils.pipeline_snapshot import build_snapshot, verify_snapshot
    from scheduler import queue
    PipelineDB(pipeline.root / "db/pipeline.db")
    for language in ("pt", "pt-br", "en", "es"):
        queue._save_queue(language, {"language": language, "items": [], "uploads_today": 0, "last_upload_at": None})
    monkeypatch.setenv("PIPELINE_STATE_REQUIRED", "true")
    monkeypatch.setenv("PIPELINE_STATE_NAMESPACE", "validation-test")
    monkeypatch.setattr(pipeline_state, "require_ready", lambda *args: {})
    seen = []
    def save(base, *, reason):
        snapshot = build_snapshot(base, base / "db/pipeline.db", snapshot_id=reason, namespace="validation-test", run_id="123", commit="abc123")
        verify_snapshot(snapshot)
        seen.append(reason)
        return {}
    monkeypatch.setattr(pipeline_state, "checkpoint_from_environment", save)
    main.run_pipeline(pipeline.config, ["pt"], test_story=True)
    assert seen[0] == "source_registered" and seen[-1] == "language_exported"
