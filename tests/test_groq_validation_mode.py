from pathlib import Path
import os
import shutil
import subprocess

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


@pytest.mark.parametrize("event", ["workflow_dispatch", "schedule"])
def test_provedor_configurado_groq_completa_rotina_sem_mudar_namespace(event):
    result = execution(event=event, configured_provider="groq")
    assert result["llm_provider"] == "groq"
    assert result["namespace"] == "production" and result["generate"] and result["publish"]


@pytest.mark.parametrize("provider", ["", "other", "groq;echo segredo", None])
def test_provedor_configurado_invalido_bloqueia(provider):
    with pytest.raises(StateError):
        execution(event="schedule", configured_provider=provider)


def test_catalogo_gemini_nao_pode_usar_groq_configurado():
    with pytest.raises(StateError):
        execution(event="workflow_dispatch", configured_provider="groq",
                  gemini_catalog_only=True, only_generate=True)


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
                 "INPUT_LEGACY_CACHE_RUN_ID", "INPUT_LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "github-output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setenv("GITHUB_EVENT_NAME", event)
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("INPUT_GROQ_VALIDATION", "true")
    assert pipeline_execution.main() == 0
    assert f"llm_provider={provider}\n" in output.read_text(encoding="utf-8")


def test_cli_le_provedor_do_repositorio(monkeypatch, tmp_path):
    from utils import pipeline_execution
    for name in ("INPUT_STATE_ACTION", "INPUT_VALIDATION_NAMESPACE", "INPUT_DRY_RUN",
                 "INPUT_ONLY_GENERATE", "INPUT_TEST_STORY", "INPUT_GEMINI_CATALOG_ONLY",
                 "INPUT_LEGACY_CACHE_RUN_ID", "INPUT_GROQ_VALIDATION"):
        monkeypatch.delenv(name, raising=False)
    output = tmp_path / "github-output"
    for name, value in {"GITHUB_OUTPUT": str(output), "GITHUB_EVENT_NAME": "schedule",
                        "GITHUB_REF": "refs/heads/main", "GITHUB_RUN_ID": "123",
                        "INPUT_LLM_PROVIDER": "groq"}.items():
        monkeypatch.setenv(name, value)
    assert pipeline_execution.main() == 0
    assert "llm_provider=groq\n" in output.read_text(encoding="utf-8")


def test_workflow_groq_manual_nao_usa_gemini_nem_altera_cron():
    path = Path(__file__).resolve().parents[1] / ".github/workflows/pipeline.yml"
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    assert data["on"]["workflow_dispatch"]["inputs"]["validacao_groq"]["default"] == "false"
    steps = {step["id"]: step for step in data["jobs"]["gerar-e-publicar"]["steps"] if "id" in step}
    assert "INPUT_GROQ_VALIDATION" in steps["execution"]["env"]
    assert "vars.PIPELINE_LLM_PROVIDER" in steps["execution"]["env"]["INPUT_LLM_PROVIDER"]
    assert "steps.execution.outputs.llm_provider == 'gemini'" in steps["generation_window"]["if"]
    assert "steps.execution.outputs.llm_provider == 'groq'" in steps["generate"]["if"]
    env = steps["generate"]["env"]
    for name in ("GROQ_API_KEY", "GROQ_API_KEY_PT", "GROQ_API_KEY_EN", "GROQ_API_KEY_ES"):
        assert env[name] == "${{ steps.execution.outputs.llm_provider == 'groq' && secrets." + name + " || '' }}"
    assert env["GEMINI_API_KEY"] == "${{ steps.execution.outputs.llm_provider == 'gemini' && secrets.GEMINI_API_KEY || '' }}"
    assert '"$PIPELINE_LLM_PROVIDER" == "gemini"' in steps["generate"]["run"]
    assert '"$PIPELINE_GROQ_VALIDATION" == "true"' in steps["generate"]["run"]
    assert "python scripts/generate_daily_batch.py --target 1" in steps["generate"]["run"]
    assert "generate_daily_batch.py" in steps["generate"]["run"]


@pytest.mark.parametrize("provider,validation,expected", [
    ("groq", "true", ["scripts/generate_daily_batch.py --target 1 --lang pt"]),
    ("groq", "false", ["scripts/generate_daily_batch.py --lang pt"]),
    ("gemini", "false", ["scripts/check_gemini.py", "scripts/generate_daily_batch.py --lang pt"]),
])
def test_comando_real_do_workflow_exige_lote_no_groq_e_preserva_gemini(provider, validation, expected):
    bash = shutil.which("bash")
    if not bash and Path("C:/Program Files/Git/bin/bash.exe").is_file():
        bash = "C:/Program Files/Git/bin/bash.exe"
    if not bash:
        pytest.skip("Bash não instalado")
    path = Path(__file__).resolve().parents[1] / ".github/workflows/pipeline.yml"
    data = yaml.load(path.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    step = next(s for s in data["jobs"]["gerar-e-publicar"]["steps"] if s.get("id") == "generate")
    environment = {**os.environ, "PIPELINE_LLM_PROVIDER": provider, "PIPELINE_GROQ_VALIDATION": validation,
                   "PIPELINE_LANGUAGES": "pt",
                   "PIPELINE_DRY_RUN": "false", "PIPELINE_TEST_STORY": "false",
                   "PIPELINE_GEMINI_CATALOG_ONLY": "false"}
    # Só captura a chamada: não executa Python, API, geração ou publicação.
    result = subprocess.run([bash, "-e", "-c", 'python() { printf "%s\\n" "$*"; };\n' + step["run"]],
                            env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == expected
