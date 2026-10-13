"""Contrato do provedor gratuito com transporte falso, sem consumir a API."""

import json
from types import SimpleNamespace

import pytest

from utils import environment as env, telemetry


@pytest.fixture(autouse=True)
def gemini_env(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "segredo-sintetico")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("GEMINI_MIN_INTERVAL_SECONDS", "0")
    telemetry.reset()


def response(text="Texto completo.", finish="STOP", **extra):
    return {"candidates": [{"finishReason": finish, "content": {"parts": [{"text": text}]}}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5,
                              "totalTokenCount": 18, "thoughtsTokenCount": 3}, **extra}


def fake_transport(monkeypatch, body=None, status=200, headers=None, error=None):
    from utils import gemini_client
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))
        if error:
            raise error
        return SimpleNamespace(status_code=status, headers=headers or {},
                               json=lambda: body if body is not None else response(), close=lambda: None)

    monkeypatch.setattr(gemini_client.requests, "post", post)
    return calls


def create(**kwargs):
    from utils.llm_client import tracked_llm
    return tracked_llm(env.llm_api_key("en"), "adapter", timeout=5).chat.completions.create(
        model="modelo-groq-legado", messages=[{"role": "system", "content": "Instrução."},
                                             {"role": "user", "content": "Fonte literal."}], **kwargs)


def test_selecao_nao_reutiliza_chave_groq_com_gemini_ausente(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GROQ_API_KEY_EN", "groq-privado")
    assert env.llm_api_key("en", "legado") == ""


def test_provedor_invalido_bloqueia_em_vez_de_fallback(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "typo")
    with pytest.raises(ValueError):
        env.llm_api_key("en")


def test_transporte_preserva_mensagens_limites_e_consumo(monkeypatch):
    calls = fake_transport(monkeypatch)
    result = create(max_tokens=3000, temperature=.3)
    url, options = calls[0]
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
    assert "segredo" not in url
    assert options["headers"]["x-goog-api-key"] == "segredo-sintetico"
    assert options["allow_redirects"] is False and options["timeout"] == 5
    payload = options["json"]
    assert payload["systemInstruction"]["parts"] == [{"text": "Instrução."}]
    assert payload["contents"] == [{"role": "user", "parts": [{"text": "Fonte literal."}]}]
    assert payload["generationConfig"] == {"maxOutputTokens": 3000, "temperature": .3,
                                           "thinkingConfig": {"thinkingBudget": 0}}
    assert result.choices[0].message.content == "Texto completo."
    assert result.choices[0].finish_reason == "stop"
    assert telemetry.usage_by_stage()["adapter"]["total"] == 18
    assert telemetry._models["adapter"] == "gemini-2.5-flash"


@pytest.mark.parametrize("mode", ["facts", "chunk", "global"])
def test_guardiao_recebe_schema_completo_e_mesmos_gates(monkeypatch, mode):
    from stages.script_guardian import _GroqReviewer, _semantic_response_format
    text = json.dumps({"facts": []} if mode == "facts" else {"approved": True, "issues": []})
    calls = fake_transport(monkeypatch, response(text))
    reviewer = _GroqReviewer({"groq_model": "qwen/qwen3.8-27b", "semantic_timeout_seconds": 5})
    assert reviewer.review(language="pt", mode=mode, source_chunk="Fonte.") == text
    generation = calls[0][1]["json"]["generationConfig"]
    assert generation["responseMimeType"] == "application/json"
    assert generation["responseJsonSchema"] == _semantic_response_format("qwen/qwen3.8-27b", mode)["json_schema"]["schema"]
    assert generation["maxOutputTokens"] == 2048


@pytest.mark.parametrize("finish", ["MAX_TOKENS", "SAFETY", "RECITATION", "OTHER", None])
def test_resposta_incompleta_ou_bloqueada_nao_e_texto_aprovado(monkeypatch, finish):
    from utils.gemini_client import GeminiError
    fake_transport(monkeypatch, response('{"approved":true,"issues":[]}', finish))
    with pytest.raises(GeminiError, match="incomplete_response"):
        create(max_tokens=2048)


def test_sem_candidato_bloqueia_sem_vazar_feedback(monkeypatch):
    from utils.gemini_client import GeminiError
    fake_transport(monkeypatch, {"promptFeedback": {"blockReason": "PRIVADO"}})
    with pytest.raises(GeminiError) as caught:
        create()
    assert "PRIVADO" not in str(caught.value)


def test_http429_preserva_retryinfo_sem_guardar_mensagem_chave_ou_corpo(monkeypatch):
    from utils.gemini_client import GeminiError
    from stages.script_guardian import _provider_failure, _retry_wait
    body = {"error": {"status": "RESOURCE_EXHAUSTED", "message": "SEGREDO E TEXTO PRIVADO",
                      "details": [{"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "42s"}]}}
    calls = fake_transport(monkeypatch, body, status=429)
    from utils.llm_client import tracked_llm
    with pytest.raises(GeminiError) as caught:
        tracked_llm(env.llm_api_key(), "script_guardian", retry_rate_limit=False).chat.completions.create(
            model="qwen/qwen3.8-27b", messages=[{"role": "user", "content": "Fonte."}])
    assert len(calls) == 1
    assert _retry_wait(caught.value, 15) == 42
    failure = _provider_failure(caught.value, "global", 1, 50)
    assert failure.code == "rate_limit" and failure.http_status == 429
    assert failure.retry_after_seconds == 42
    assert "SEGREDO" not in str(caught.value) + repr(vars(caught.value))


@pytest.mark.parametrize("status,expected", [(400, "provider_error"), (401, "authentication"),
                                            (403, "authorization"), (503, "provider_error")])
def test_erros_http_continuam_classificados_e_sanitizados(monkeypatch, status, expected):
    from utils.gemini_client import GeminiError
    from stages.script_guardian import _provider_failure
    fake_transport(monkeypatch, {"error": {"message": "NUNCA_LOGAR"}}, status=status)
    with pytest.raises(GeminiError) as caught:
        create()
    assert _provider_failure(caught.value, "facts", 1, 10).code == expected
    assert "NUNCA_LOGAR" not in str(caught.value)


def test_timeout_sanitizado_e_reconhecido(monkeypatch):
    import requests
    from stages.script_guardian import _provider_failure
    fake_transport(monkeypatch, error=requests.Timeout("CHAVE_E_URL_PRIVADAS"))
    with pytest.raises(TimeoutError) as caught:
        create()
    assert _provider_failure(caught.value, "facts", 1, 10).code == "timeout"
    assert "PRIVADAS" not in str(caught.value)


def test_groq_padrao_preserva_cliente_e_parametros(monkeypatch):
    from utils import groq_client
    from utils.llm_client import tracked_llm
    monkeypatch.delenv("PIPELINE_LLM_PROVIDER")
    monkeypatch.setattr(env, "groq_api_key", lambda language: "chave-legada")
    monkeypatch.setattr(groq_client, "tracked_groq", lambda key, stage, **options: (key, stage, options))
    assert env.llm_api_key("pt") == "chave-legada"
    assert tracked_llm("chave-legada", "adapter", timeout=5) == ("chave-legada", "adapter", {"timeout": 5})


def test_modelo_sem_modalidade_gratuita_nao_e_selecionado(monkeypatch):
    from utils.gemini_client import GeminiClient
    monkeypatch.setenv("GEMINI_MODEL", "gemini-modelo-pago")
    with pytest.raises(ValueError):
        GeminiClient("chave", "adapter")


@pytest.mark.parametrize("stage", ["adapter", "narrator_profile", "gender_detector", "naturalizer",
                                  "metadata", "titler_title", "titler_hook", "titler_closing", "validator"])
def test_todas_as_etapas_usam_gemini_sem_chamar_groq(monkeypatch, stage):
    from utils import groq_client
    def forbidden(*args, **kwargs):
        raise AssertionError("Etapa tentou consumir o Groq")
    monkeypatch.setattr(groq_client, "tracked_groq", forbidden)
    text = '{"evidence":[]}' if stage == "narrator_profile" else "Minha irmã exigiu toda a herança."
    calls = fake_transport(monkeypatch, response(text))
    if stage == "adapter":
        from stages.adapter import StoryAdapter
        result = StoryAdapter({}).adapt({"title": "Inheritance", "text": "My sister asked for the money."})
        assert result["adapted_by"] == "gemini"
    elif stage == "narrator_profile":
        from stages.narrator_profile import NarratorProfileResolver
        from utils.text_chunks import split_lossless
        assert NarratorProfileResolver({})._groq_evidence(split_lossless("I work here.", 100)[0]) == []
    elif stage == "gender_detector":
        from stages.gender_detector import GenderDetector
        assert GenderDetector({})._correct_via_groq("Eu sou cansado.", "female", "pt") == text
    elif stage == "naturalizer":
        from stages.naturalizer import ScriptNaturalizer
        assert ScriptNaturalizer({})._groq_rewrite("Fonte.", "pt", "female") == text
    elif stage == "metadata":
        from stages.metadata import MetadataGenerator
        assert MetadataGenerator({})._description_via_groq("Título", "Fonte.", "pt", "female") == text
    elif stage.startswith("titler_"):
        from stages.titler import TitleGenerator
        method = getattr(TitleGenerator({}), "_groq_" + stage.split("_")[1])
        assert method("Inheritance", "Fonte.", "pt")
    else:
        from stages.validator import ValidatorEngine
        assert ValidatorEngine({"groq_call_delay": 0})._call_groq("Instrução.", "Fonte.", language="pt") == text
    assert len(calls) == 1
    assert calls[0][1]["headers"]["x-goog-api-key"] == "segredo-sintetico"


def test_guardiao_nao_repete_resposta_truncada_com_json_valido(monkeypatch, tmp_path):
    from stages.script_guardian import ScriptGuardian, _ReviewUnavailable
    calls = fake_transport(monkeypatch, response('{"approved":true,"issues":[]}', "MAX_TOKENS"))
    guardian = ScriptGuardian({"semantic_retry_wait_seconds": 0}, base_dir=tmp_path)
    with pytest.raises(_ReviewUnavailable) as caught:
        guardian._request(mode="global", source_text="Fonte.", source_chunk="Fonte.",
                          candidate_text="Fonte.", language="pt")
    assert caught.value.failure.code == "incomplete_response"
    assert len(calls) == 1


def test_retry_de_geracao_limitado_sem_repetir_espera_acima_do_teto(monkeypatch):
    from utils import gemini_client
    from utils.llm_client import tracked_llm
    calls = fake_transport(monkeypatch, {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "42s"}]}}, status=429)
    waits = []
    monkeypatch.setattr(gemini_client, "_sleep", waits.append)
    with pytest.raises(gemini_client.GeminiError):
        tracked_llm(env.llm_api_key(), "adapter").chat.completions.create(
            messages=[{"role": "user", "content": "Fonte."}])
    assert len(calls) == 1 and waits == []


def test_cadencia_compartilhada_entre_etapas(monkeypatch):
    from utils import gemini_client
    monkeypatch.setenv("GEMINI_MIN_INTERVAL_SECONDS", "13")
    monkeypatch.setattr(gemini_client, "_NEXT_REQUEST_AT", {})
    clock = iter([0, 0, 1, 1])
    monkeypatch.setattr(gemini_client.time, "monotonic", lambda: next(clock))
    waits = []
    monkeypatch.setattr(gemini_client, "_sleep", waits.append)
    calls = fake_transport(monkeypatch)
    for stage in ("adapter", "script_guardian"):
        gemini_client.GeminiClient("chave", stage).chat.completions.create(
            messages=[{"role": "user", "content": "Fonte."}])
    assert len(calls) == 2 and waits == [12]


def test_workflow_gemini_usa_secret_so_na_geracao_e_producao_continua_groq():
    from pathlib import Path
    import yaml
    data = yaml.load((Path(__file__).resolve().parents[1] / ".github/workflows/pipeline.yml").read_text(
        encoding="utf-8"), Loader=yaml.BaseLoader)
    inputs = data["on"]["workflow_dispatch"]["inputs"]
    assert inputs["llm_provider"]["default"] == "groq"
    assert inputs["llm_provider"]["options"] == ["groq", "gemini"]
    steps = data["jobs"]["gerar-e-publicar"]["steps"]
    secret_steps = [s for s in steps if "GEMINI_API_KEY" in s.get("env", {})]
    assert len(secret_steps) == 1 and secret_steps[0]["id"] == "generate"
    assert secret_steps[0]["env"]["GEMINI_API_KEY"] == "${{ secrets.GEMINI_API_KEY }}"
    assert secret_steps[0]["if"] == "${{ steps.execution.outputs.generate == 'true' }}"
    from utils.pipeline_execution import resolve_execution
    execution = resolve_execution(event="workflow_dispatch", ref="refs/heads/gemini-provider",
                                  run_id="123", only_generate=True, test_story=True)
    assert execution["namespace"] == "validation-123" and execution["publish"] is False
