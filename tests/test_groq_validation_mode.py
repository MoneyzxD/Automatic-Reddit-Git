from pathlib import Path

import pytest
import yaml

from utils.pipeline_execution import resolve_execution
from utils.pipeline_state import StateError


def execution(**options):
    return resolve_execution(ref="refs/heads/main", run_id="123", **options)


def test_validacao_groq_manual_real_permite_gerar_e_publicar():
    result = execution(event="workflow_dispatch", groq_validation=True)
    assert result["llm_provider"] == "groq"
    assert result["namespace"] == "production" and result["generate"] and result["publish"]


def test_cron_e_manual_padrao_continuam_gemini():
    assert execution(event="workflow_dispatch")["llm_provider"] == "gemini"
    assert execution(event="schedule", groq_validation=True)["llm_provider"] == "gemini"


def test_validacao_groq_sintetica_permanece_sem_publicacao():
    result = execution(event="workflow_dispatch", groq_validation=True, test_story=True)
    assert result["llm_provider"] == "groq" and result["namespace"] == "validation-123"
    assert not result["publish"]


@pytest.mark.parametrize("options", [
    {"groq_validation": "true"},
    {"groq_validation": True, "gemini_catalog_only": True, "only_generate": True},
])
def test_modo_groq_rejeita_opcoes_incompativeis(options):
    with pytest.raises(StateError):
        execution(event="workflow_dispatch", **options)


@pytest.mark.parametrize("event,provider", [("workflow_dispatch", "groq"), ("schedule", "gemini")])
def test_cli_propaga_provedor_resolvido_sem_entrada_livre(monkeypatch, tmp_path, event, provider):
    from utils import pipeline_execution
    for name in ("INPUT_STATE_ACTION", "INPUT_VALIDATION_NAMESPACE", "INPUT_DRY_RUN",
                 "INPUT_ONLY_GENERATE", "INPUT_TEST_STORY", "INPUT_GEMINI_CATALOG_ONLY",
                 "INPUT_LEGACY_CACHE_RUN_ID"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("INPUT_GROQ_VALIDATION", "true")
    assert pipeline_execution.main() == 0
    assert f"llm_provider={provider}\n" in output.read_text(encoding="utf-8")


def test_workflow_groq_manual_nao_usa_gemini_nem_altera_cron():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/pipeline.yml"
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert data["on"]["workflow_dispatch"]["inputs"]["validacao_groq"]["default"] == "false"
    steps = {step["id"]: step for step in data["jobs"]["gerar-e-publicar"]["steps"] if "id" in step}
    assert "INPUT_GROQ_VALIDATION" in steps["execution"]["env"]
    assert "steps.execution.outputs.llm_provider == 'gemini'" in steps["generation_window"]["if"]
    assert "steps.execution.outputs.llm_provider == 'groq'" in steps["generate"]["if"]
    env = steps["generate"]["env"]
    for name in ("GROQ_API_KEY", "GROQ_API_KEY_PT", "GROQ_API_KEY_EN", "GROQ_API_KEY_ES"):
        assert env[name] == "${{ steps.execution.outputs.llm_provider == 'groq' && secrets." + name + " || '' }}"
    assert env["GEMINI_API_KEY"] == "${{ steps.execution.outputs.llm_provider == 'gemini' && secrets.GEMINI_API_KEY || '' }}"
    assert '"$PIPELINE_LLM_PROVIDER" == "gemini"' in steps["generate"]["run"]
    assert '"$PIPELINE_LLM_PROVIDER" == "groq"' in steps["generate"]["run"]
    assert "python main.py --lang $PIPELINE_LANGUAGES" in steps["generate"]["run"]
    assert "generate_daily_batch.py" in steps["generate"]["run"]
