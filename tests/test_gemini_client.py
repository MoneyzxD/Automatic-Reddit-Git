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
    from utils import gemini_client
    monkeypatch.setattr(gemini_client, "_NEXT_REQUEST_AT", {})
    monkeypatch.setattr(gemini_client, "_sleep", lambda seconds: None)
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


@pytest.mark.parametrize("selection", [None, "", "  "])
def test_padrao_gemini_ignora_chaves_groq_existentes(monkeypatch, selection):
    from utils import groq_client
    if selection is None:
        monkeypatch.delenv("PIPELINE_LLM_PROVIDER")
    else:
        monkeypatch.setenv("PIPELINE_LLM_PROVIDER", selection)
    monkeypatch.setenv("GROQ_API_KEY", "legado-nao-usar")
    monkeypatch.setenv("GROQ_API_KEY_EN", "legado-nao-usar")
    def forbidden(*args, **kwargs):
        raise AssertionError("Default tentou usar Groq")
    monkeypatch.setattr(groq_client, "tracked_groq", forbidden)
    calls = fake_transport(monkeypatch)
    assert env.llm_provider() == "gemini"
    assert create().choices[0].message.content == "Texto completo."
    assert calls[0][1]["headers"]["x-goog-api-key"] == "segredo-sintetico"


def test_guardiao_gemini_resolve_ancoras_e_duas_listas_sem_perder_texto(monkeypatch):
    from utils import gemini_client
    from stages.script_guardian import _GroqReviewer, parse_semantic_review
    candidate = "mim mesma. " + "Contexto preservado. " * 25 + "Eu cuido de mim mesma. 🧾"
    captured = {}
    def post(url, **options):
        captured.update(options["json"])
        wire = json.loads(captured["contents"][0]["parts"][0]["text"])
        assert "candidate_text" not in wire
        assert "".join(unit["text"] for unit in wire["candidate_units"]) == candidate
        uid = next(unit["id"] for unit in reversed(wire["candidate_units"]) if "mim mesma" in unit["text"])
        finding = {"original": "mim mesma", "replacement": "mim mesmo", "category": "narrator_gender",
                   "severity": "critical", "subject": "narrator", "reason": "Perfil masculino",
                   "source_quote_id": "s0", "candidate_unit_ids": [uid]}
        body = response(json.dumps({"approved": False, "issues": [finding], "language_issues": []}))
        return SimpleNamespace(status_code=200, headers={}, json=lambda: body, close=lambda: None)
    monkeypatch.setattr(gemini_client.requests, "post", post)
    result = _GroqReviewer({"semantic_timeout_seconds": 5}).review(
        language="pt", mode="chunk", source_chunk="A male narrator cares for himself.",
        candidate_text=candidate, factual_context="[]")
    review = parse_semantic_review(result)
    assert review.patches[0].start == candidate.rindex("mim mesma")
    assert review.patches[0].source_quote == "A male narrator cares for himself."
    schema = captured["generationConfig"]["responseJsonSchema"]
    assert set(schema["properties"]) == {"approved", "issues", "language_issues"}
    assert "start" not in schema["properties"]["issues"]["items"]["properties"]


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


def test_groq_explicito_preserva_cliente_e_parametros(monkeypatch):
    from utils import groq_client
    from utils.llm_client import tracked_llm
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
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


@pytest.mark.parametrize("stage", ["adapter", "naturalizer", "title", "hook", "closing", "metadata", "gender"])
def test_falha_gemini_interrompe_geracao_sem_ollama_regras_ou_templates(monkeypatch, stage):
    from utils.llm_client import LLMUnavailable
    fake_transport(monkeypatch, {"error": {"details": [
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "42s"}]}}, status=429)
    def forbidden(*args, **kwargs):
        pytest.fail("Falha Gemini não pode gerar por outro caminho")
    if stage == "adapter":
        from stages.adapter import StoryAdapter
        obj = StoryAdapter({})
        monkeypatch.setattr(obj, "_build_clean_script", forbidden)
        invoke = lambda: obj.adapt({"title": "Title", "text": "A complete source."})
    elif stage == "naturalizer":
        from stages.naturalizer import ScriptNaturalizer
        obj = ScriptNaturalizer({})
        monkeypatch.setattr(obj, "_ollama_rewrite", forbidden)
        monkeypatch.setattr(obj, "_rule_based_rewrite", forbidden)
        invoke = lambda: obj.naturalize("Texto completo.", "pt", "male")
    elif stage in {"title", "hook", "closing"}:
        from stages.titler import TitleGenerator
        obj = TitleGenerator({})
        monkeypatch.setattr(obj, "_ollama_" + stage, forbidden)
        method = {"title": "generate", "hook": "generate_hook", "closing": "generate_closing_hook"}[stage]
        invoke = lambda: getattr(obj, method)("Texto completo.", "pt", original_title="Title")
    elif stage == "metadata":
        from stages.metadata import MetadataGenerator
        obj = MetadataGenerator({})
        monkeypatch.setattr(obj, "_description_via_template", forbidden)
        invoke = lambda: obj.generate({"title": "Title", "text": "Fonte."}, "pt")
    else:
        from stages.gender_detector import GenderDetector
        obj = GenderDetector({})
        monkeypatch.setattr(obj, "_correct_via_ollama", forbidden)
        invoke = lambda: obj.validate_and_fix("Texto completo.", "male", "pt")
    with pytest.raises(LLMUnavailable):
        invoke()


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


def test_workflow_manual_e_cron_usam_gemini_sem_secrets_groq():
    from pathlib import Path
    import yaml
    data = yaml.load((Path(__file__).resolve().parents[1] / ".github/workflows/pipeline.yml").read_text(
        encoding="utf-8"), Loader=yaml.BaseLoader)
    inputs = data["on"]["workflow_dispatch"]["inputs"]
    assert "llm_provider" not in inputs
    steps = data["jobs"]["gerar-e-publicar"]["steps"]
    secret_steps = [s for s in steps if "GEMINI_API_KEY" in s.get("env", {})]
    assert len(secret_steps) == 1 and secret_steps[0]["id"] == "generate"
    assert secret_steps[0]["env"]["GEMINI_API_KEY"] == "${{ secrets.GEMINI_API_KEY }}"
    assert secret_steps[0]["env"]["PIPELINE_LLM_PROVIDER"] == "gemini"
    assert not any(key.startswith("GROQ_API_KEY") for step in steps for key in step.get("env", {}))
    assert "steps.execution.outputs.generate == 'true'" in secret_steps[0]["if"]
    assert "steps.generation_window.outputs.allowed == 'true'" in secret_steps[0]["if"]
    from utils.pipeline_execution import resolve_execution
    execution = resolve_execution(event="workflow_dispatch", ref="refs/heads/gemini-provider",
                                  run_id="123", only_generate=True, test_story=True)
    assert execution["namespace"] == "validation-123" and execution["publish"] is False


def test_catalogo_mostra_somente_modelos_publicos_aptos_a_geracao(monkeypatch):
    from scripts.check_gemini import check_catalog
    from utils import gemini_client
    calls = []
    def get(url, **options):
        calls.append((url, options))
        return SimpleNamespace(status_code=200, close=lambda: None, json=lambda: {"models": [
            {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
            {"name": "models/gemini-embedding", "supportedGenerationMethods": ["embedContent"]},
            {"name": "NAO_LOGAR\nPRIVADO", "supportedGenerationMethods": ["generateContent"]}]})
    monkeypatch.setattr(gemini_client.requests, "get", get)
    assert check_catalog() == ["gemini-2.5-flash"]
    assert calls[0][0] == "https://generativelanguage.googleapis.com/v1beta/models"
    assert calls[0][1]["headers"]["x-goog-api-key"] == "segredo-sintetico"
    assert calls[0][1]["allow_redirects"] is False


def test_catalogo_http_falho_nao_vaza_corpo(monkeypatch):
    from scripts.check_gemini import check_catalog
    from utils import gemini_client
    monkeypatch.setattr(gemini_client.requests, "get", lambda *a, **k:
                        SimpleNamespace(status_code=403, json=lambda: {"error": "PRIVADO"}, close=lambda: None))
    with pytest.raises(gemini_client.GeminiError) as caught:
        check_catalog()
    assert caught.value.status_code == 403 and "PRIVADO" not in str(caught.value)


def test_catalogo_nao_pode_publicar_mesmo_com_modo_publish(monkeypatch, tmp_path):
    from utils.pipeline_execution import main
    for name, value in {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                        "GITHUB_RUN_ID": "123", "GITHUB_OUTPUT": str(tmp_path / "output"),
                        "INPUT_STATE_ACTION": "publish", "INPUT_GEMINI_CATALOG_ONLY": "true",
                        "INPUT_ONLY_GENERATE": "false", "INPUT_TEST_STORY": "false",
                        "INPUT_DRY_RUN": "false"}.items():
        monkeypatch.setenv(name, value)
    assert main() == 2
    assert not (tmp_path / "output").exists()


@pytest.mark.parametrize("options", [{"state_action": "verify"}, {"state_action": "bootstrap"},
                                    {"only_generate": False}, {"dry_run": True}])
def test_catalogo_bloqueia_modos_incompativeis(options):
    from utils.pipeline_execution import resolve_execution
    from utils.pipeline_state import StateError
    kwargs = {"event": "workflow_dispatch", "ref": "refs/heads/gemini-provider", "run_id": "123",
              "only_generate": True, "gemini_catalog_only": True, **options}
    with pytest.raises(StateError):
        resolve_execution(**kwargs)


def test_catalogo_valido_resolve_so_namespace_de_validacao():
    from utils.pipeline_execution import resolve_execution
    result = resolve_execution(event="workflow_dispatch", ref="refs/heads/main", run_id="123",
                               gemini_catalog_only=True, only_generate=True)
    assert result["namespace"] == "validation-123" and not result["publish"]


def test_modelo_atual_validado_no_catalogo_preserva_schema_e_cap(monkeypatch):
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.8-flash")
    from stages.script_guardian import _GroqReviewer, _semantic_response_format
    calls = fake_transport(monkeypatch, response('{"facts":[]}'))
    _GroqReviewer({"groq_model": "qwen/qwen3.8-27b", "semantic_timeout_seconds": 5}).review(
        language="en", mode="facts", source_chunk="I work here.")
    url, options = calls[0]
    assert url.endswith("/models/gemini-3.8-flash:generateContent")
    generation = options["json"]["generationConfig"]
    assert generation["thinkingConfig"] == {"thinkingLevel": "low"}
    assert generation["maxOutputTokens"] == 2048
    assert "temperature" not in generation
    assert generation["responseJsonSchema"] == _semantic_response_format(
        "qwen/qwen3.8-27b", "facts")["json_schema"]["schema"]


def gemini_translator(monkeypatch):
    from stages.translator import ScriptTranslator
    translator = ScriptTranslator({"delay": 0, "retry_waits": [0, 0]})
    for name in ("_translate_chunk_google", "_translate_chunk_mymemory"):
        monkeypatch.setattr(translator, name, lambda *a: pytest.fail("Provedor legado não deve ser usado"))
    return translator


def test_deteccao_idioma_gemini_nao_consulta_google(monkeypatch):
    from deep_translator import GoogleTranslator
    from stages.translator import ScriptTranslator
    monkeypatch.setattr(GoogleTranslator, "translate", lambda *a: pytest.fail("Google não deve ser consultado"))
    assert ScriptTranslator({}).detect_language(" the story was told with this and that ") == "en"


def test_traducao_gemini_preserva_whitespace_e_provedor(monkeypatch):
    calls = fake_transport(monkeypatch, response("Eu trabalho aqui."))
    result = gemini_translator(monkeypatch).translate("\nI work here.\n", "en", "pt")
    assert result.require_text() == "\nEu trabalho aqui.\n" and result.provider == "Gemini"
    assert len(calls) == 1
    assert calls[0][1]["json"]["generationConfig"]["maxOutputTokens"] == 4096


@pytest.mark.parametrize("finish", ["MAX_TOKENS", "SAFETY"])
def test_traducao_gemini_incompleta_nunca_retorna_fonte(monkeypatch, finish):
    fake_transport(monkeypatch, response("Eu trabalho aqui.", finish))
    result = gemini_translator(monkeypatch).translate("I work here.", "en", "pt")
    assert result.status == "unavailable" and result.text is None


def test_traducao_gemini_rejeita_idioma_fonte_e_nao_muda_para_google(monkeypatch):
    calls = fake_transport(monkeypatch, response("I work here."))
    result = gemini_translator(monkeypatch).translate("I work here.", "en", "pt")
    assert result.status == "rejected" and result.text is None and len(calls) == 1


def test_traducao_gemini_preserva_sentinelas_do_glossario(monkeypatch):
    translator = gemini_translator(monkeypatch)
    monkeypatch.setattr(translator, "_translate_chunk_gemini", lambda chunk, *_: chunk.replace("I bought a", "Comprei uma"))
    assert translator.translate("I bought a Pokemon card", "en", "pt").require_text() == "Comprei uma carta Pokémon"


def test_traducao_gemini_nao_reutiliza_cache_legado(monkeypatch, tmp_path):
    import hashlib
    source = "This changed."
    translator = gemini_translator(monkeypatch)
    target = tmp_path / "pt/script_example_pt.txt"
    target.parent.mkdir()
    target.write_text("Isso mudou.", encoding="utf-8")
    target.with_suffix(".cache.json").write_text(json.dumps({
        "source_sha256": hashlib.sha256(source.encode()).hexdigest(), "source_lang": "en",
        "target_lang": "pt", "glossary_version": translator.glossary.version}), encoding="utf-8")
    calls = fake_transport(monkeypatch, response("Isto se alterou."))
    result = translator.translate_all(source, "example", tmp_path, ["pt"], source_lang="en")["pt"]
    assert result.provider == "Gemini" and result.require_text() == "Isto se alterou." and len(calls) == 1
    assert json.loads(target.with_suffix(".cache.json").read_text(encoding="utf-8"))["translation_provider"] == "Gemini"


def test_traducao_gemini_usa_blocos_maiores_sem_perder_fonte(monkeypatch):
    source = "I work here. " * 500
    calls = fake_transport(monkeypatch, response("Eu trabalho aqui."))
    result = gemini_translator(monkeypatch).translate(source, "en", "pt")
    assert result.status == "approved" and len(calls) == 2
    assert "".join(chunk.source_text for chunk in result.chunks) == source


def test_503_de_geracao_tem_um_retry_limitado_com_payload_identico(monkeypatch):
    from utils import gemini_client
    calls, waits = [], []
    def post(url, **options):
        calls.append(options["json"])
        status = 503 if len(calls) == 1 else 200
        return SimpleNamespace(status_code=status, headers={}, close=lambda: None,
                               json=lambda: response() if status == 200 else {"error": {"message": "PRIVADO"}})
    monkeypatch.setattr(gemini_client.requests, "post", post)
    monkeypatch.setattr(gemini_client, "_sleep", waits.append)
    assert create().choices[0].message.content == "Texto completo."
    assert len(calls) == 2 and calls[0] == calls[1] and waits == [15]


@pytest.mark.parametrize("failure", ["timeout", "connection"])
def test_falha_transitoria_de_transporte_tem_um_retry_sem_mudar_limites(monkeypatch, failure):
    import requests
    from utils import gemini_client
    calls, waits = [], []
    exception = requests.Timeout if failure == "timeout" else requests.ConnectionError
    def post(url, **options):
        calls.append((url, options))
        if len(calls) == 1:
            raise exception("CHAVE_E_URL_PRIVADAS")
        return SimpleNamespace(status_code=200, headers={}, close=lambda: None, json=response)
    monkeypatch.setattr(gemini_client.requests, "post", post)
    monkeypatch.setattr(gemini_client, "_sleep", waits.append)
    assert create(max_tokens=2048).choices[0].message.content == "Texto completo."
    assert calls[0] == calls[1] and len(calls) == 2 and waits == [15]
    assert calls[1][1]["timeout"] == 5


def test_timeout_persistente_para_em_duas_tentativas_sanitizadas(monkeypatch):
    import requests
    calls = fake_transport(monkeypatch, error=requests.Timeout("CHAVE_E_URL_PRIVADAS"))
    with pytest.raises(TimeoutError) as caught:
        create()
    assert len(calls) == 2 and "PRIVADAS" not in str(caught.value)


def test_guardiao_continua_dono_do_retry_de_timeout(monkeypatch):
    import requests
    from utils.llm_client import tracked_llm
    calls = fake_transport(monkeypatch, error=requests.Timeout("CHAVE_E_URL_PRIVADAS"))
    with pytest.raises(TimeoutError):
        tracked_llm(env.llm_api_key(), "script_guardian", sdk_max_retries=0,
                    retry_rate_limit=False, timeout=5).chat.completions.create(
                        messages=[{"role": "user", "content": "Fonte."}])
    assert len(calls) == 1
