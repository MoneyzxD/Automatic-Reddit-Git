from types import SimpleNamespace

import pytest

from stages.adapter import StoryAdapter
from stages.metadata import MetadataGenerator
from stages.script_guardian import QualityRejected, QualityUnavailable
from stages.titler import TitleGenerator
from stages.validator import Issue, ValidationResult, ValidatorEngine


def test_adapter_preserva_fato_no_fim_e_todas_as_partes(monkeypatch):
    story = {"id": "long", "title": "Title", "text": ("context. " * 900) + "LATE FACT"}
    seen = []
    adapter = StoryAdapter({"llm_enabled": True, "groq_api_key": "teste", "chunk_chars": 1000})
    monkeypatch.setattr(adapter, "_adapt_chunk_via_groq", lambda chunk, index, total: seen.append(chunk) or chunk)
    result = adapter.adapt(story)
    assert "".join(seen) == story["text"]
    assert result["full_script"] == story["text"]


def test_adapter_nao_publica_resposta_parcial(monkeypatch):
    story = {"title": "Title", "text": "First fact. " * 200 + "Last fact."}
    adapter = StoryAdapter({"llm_enabled": True, "groq_api_key": "teste", "chunk_chars": 200})
    monkeypatch.setattr(adapter, "_adapt_chunk_via_groq", lambda chunk, index, total: chunk if index == 0 else None)
    result = adapter.adapt(story)
    assert result["adapted_by"] == "rules"
    assert "Last fact." in result["full_script"]


def test_adapter_preserva_atualizacao_e_dialogo():
    story = {"title": "Title", "text": "Edit: She called.\nUpdate 2: He said, \"I never left.\"\n\n> I replied yes.\nTL;DR: They reconciled."}
    result = StoryAdapter({"llm_enabled": False}).adapt(story)
    assert "She called." in result["full_script"]
    assert 'He said, "I never left."' in result["full_script"]
    assert "I replied yes." in result["full_script"]
    assert "\n\nI replied yes." in result["full_script"]
    assert "They reconciled." in result["full_script"]


def test_adapter_prompt_real_inclui_chunks_e_fato_tardio(monkeypatch):
    from utils import environment, groq_client

    story = {"title": "Title", "text": ("context. " * 900) + "LATE FACT"}
    prompts = []
    monkeypatch.setattr(environment, "groq_api_key", lambda language: "key-en")

    def complete(**kwargs):
        prompt = kwargs["messages"][1]["content"]
        prompts.append(prompt)
        chunk = prompt.split("Story text:\n", 1)[1].split("\n\nCleaned story:", 1)[0]
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=chunk))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)
    result = StoryAdapter({"llm_enabled": True, "chunk_chars": 1000}).adapt(story)
    assert result["full_script"] == story["text"]
    assert len(prompts) > 1
    assert "LATE FACT" in prompts[-1]
    assert all(f"Chunk {i} of {len(prompts)}" in prompt for i, prompt in enumerate(prompts, 1))


@pytest.mark.parametrize("method", ["generate", "generate_hook", "generate_closing_hook"])
def test_titler_usa_contexto_factual_tardio(method, monkeypatch):
    generator = TitleGenerator({})
    seen = []
    monkeypatch.setattr(generator, "_groq_title", lambda title, context, language, hook_type: seen.append(context) or "Valid title")
    monkeypatch.setattr(generator, "_groq_hook", lambda title, context, language: seen.append(context) or "Valid hook")
    monkeypatch.setattr(generator, "_groq_closing", lambda title, context, language: seen.append(context) or "Valid closing")
    getattr(generator, method)("RAW PREFIX", original_title="Title", factual_context="The surgery never happened.")
    assert "The surgery never happened." in seen[0]
    assert "RAW PREFIX" not in seen[0]


def test_validator_sem_resposta_nao_aprova(tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    result = validator._parse_validation_json(None)
    assert result.status == "unavailable"
    assert not result.approved


@pytest.mark.parametrize("raw", ["{}", '{"approved":"false","issues":[]}', "not json"])
def test_validator_json_sem_aprovacao_tipificada_nao_aprova(tmp_path, raw):
    result = ValidatorEngine({}, base_dir=tmp_path)._parse_validation_json(raw)
    assert result.status == "unavailable"
    assert not result.approved


def test_validator_nao_publica_melhor_score_reprovado(monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    monkeypatch.setattr(validator, "validate_script", lambda *args, **kwargs: ValidationResult(
        status="rejected", approved=False, score=10,
        issues=[Issue("texto", "problema", "correcao", "coerencia")], raw="{}"))
    monkeypatch.setattr(validator, "apply_surgical_fix", lambda *args, **kwargs: None)
    monkeypatch.setattr(validator, "log_attempt", lambda *args, **kwargs: None)
    with pytest.raises(QualityRejected) as error:
        validator.validate_and_fix_script("texto", "pt", "female", "story")
    assert error.value.review.attempts == 1
    assert len(error.value.review.issues) == 1


def test_validator_indisponivel_bloqueia_publicacao(monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    monkeypatch.setattr(validator, "validate_script", lambda *args, **kwargs: validator._parse_validation_json(None))
    with pytest.raises(QualityUnavailable):
        validator.validate_and_fix_script("texto", "pt", "female", "story")


@pytest.mark.parametrize("method,args", [
    ("validate_and_fix_title_hook", ("Title", "Hook", "RAW PREFIX", "pt", "story")),
    ("validate_and_fix_metadata", ("Description", [], "RAW PREFIX", "pt", "story")),
])
def test_validator_nao_publica_titulo_ou_metadata_reprovados(method, args, monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    result = ValidationResult("rejected", False, 90, [Issue("texto", "problema", "correcao", "coerencia")])
    name = "validate_title_hook" if "title" in method else "validate_metadata"
    monkeypatch.setattr(validator, name, lambda *a, **k: result)
    monkeypatch.setattr(validator, "log_attempt", lambda *a, **k: None)
    monkeypatch.setattr(validator, "send_telegram_alert", lambda *a, **k: None)
    monkeypatch.setattr(validator, "apply_title_hook_fix", lambda title, hook, *a, **k: (title, hook))
    monkeypatch.setattr(validator, "apply_metadata_fix", lambda desc, tags, *a, **k: (desc, tags))
    with pytest.raises(QualityRejected):
        getattr(validator, method)(*args)


def test_validator_issue_bloqueia_aprovacao_declarada(tmp_path):
    raw = '{"approved":true,"score":100,"issues":[{"trecho":"texto","problema":"fato errado"}]}'
    result = ValidatorEngine({}, base_dir=tmp_path)._parse_validation_json(raw)
    assert result.status == "rejected"
    assert not result.approved


@pytest.mark.parametrize("method,args", [
    ("validate_title_hook", ("Title", "Hook", "RAW PREFIX")),
    ("validate_metadata", ("Description", [], "RAW PREFIX")),
])
def test_validator_envia_contexto_validado_completo(method, args, monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    prompts = []
    monkeypatch.setattr(validator, "_call_groq", lambda **kwargs: prompts.append(kwargs["user_prompt"]) or None)
    getattr(validator, method)(*args, factual_context="LATE FACT is the true outcome.")
    assert "LATE FACT is the true outcome." in prompts[0]
    assert "RAW PREFIX" not in prompts[0]


@pytest.mark.parametrize("method,args", [
    ("apply_title_hook_fix", ("Title", "Hook", [Issue("titulo", "fato", "Reescreva o titulo", "factual")], "RAW PREFIX")),
    ("apply_metadata_fix", ("Description", [], [Issue("description", "fato", "Reescreva a descricao", "factual")], "RAW PREFIX")),
])
def test_correcao_recebe_contexto_validado_completo(method, args, monkeypatch, tmp_path):
    validator = ValidatorEngine({}, base_dir=tmp_path)
    prompts = []
    monkeypatch.setattr(validator, "_call_groq", lambda **kwargs: prompts.append(kwargs["user_prompt"]) or "Texto corrigido")
    getattr(validator, method)(*args, factual_context="LATE FACT is the true outcome.")
    assert prompts
    assert all("LATE FACT is the true outcome." in prompt and "RAW PREFIX" not in prompt for prompt in prompts)


def test_metadata_usa_script_localizado_e_contexto_validado(monkeypatch):
    generator = MetadataGenerator({})
    seen = []
    monkeypatch.setattr(generator, "_description_via_groq",
                        lambda title, summary, language, gender: seen.append(summary) or "Resumo da história.\nVocê faria o mesmo?")
    generator.generate(
        {"title": "Title", "text": "ENGLISH RAW PREFIX"}, "pt",
        localized_script="Uma história em português.",
        factual_context="A cirurgia nunca aconteceu no fim.",
    )
    assert seen == ["Uma história em português.\n\nFatos validados:\nA cirurgia nunca aconteceu no fim."]


def test_metadata_sem_contexto_usa_script_localizado(monkeypatch):
    generator = MetadataGenerator({})
    seen = []
    monkeypatch.setattr(generator, "_description_via_groq",
                        lambda title, summary, language, gender: seen.append(summary) or "Resumo da história.\nVocê faria o mesmo?")
    generator.generate({"text": "ENGLISH RAW PREFIX"}, "pt", localized_script="Texto português no fim.")
    assert seen == ["Texto português no fim."]


@pytest.mark.parametrize("method", ["generate", "generate_hook", "generate_closing_hook"])
def test_titler_rejeita_resposta_groq_interrompida(method, monkeypatch):
    from utils import environment, groq_client

    monkeypatch.setattr(environment, "groq_api_key", lambda language: "key-test")
    choice = SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="PARTIAL PUBLIC TEXT"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(choices=[choice]))))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)
    generator = TitleGenerator({})
    monkeypatch.setattr(generator, "_ollama_title", lambda *args: None)
    monkeypatch.setattr(generator, "_ollama_hook", lambda *args: None)
    monkeypatch.setattr(generator, "_ollama_closing", lambda *args: None)

    result = getattr(generator, method)("Story text", original_title="Original conflict")
    assert "PARTIAL" not in result


def test_metadata_rejeita_descricao_groq_interrompida(monkeypatch):
    from utils import environment, groq_client

    monkeypatch.setattr(environment, "groq_api_key", lambda language: "key-test")
    choice = SimpleNamespace(finish_reason="length", message=SimpleNamespace(content="PARTIAL description never finished"))
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(
        create=lambda **kwargs: SimpleNamespace(choices=[choice]))))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)
    generator = MetadataGenerator({})
    monkeypatch.setattr(generator, "_description_via_template", lambda language: "Texto completo.\nVocê faria o mesmo?")

    result = generator.generate({"title": "Title"}, "pt", localized_script="História completa.")
    assert result["description"] == "Texto completo.\nVocê faria o mesmo?"


def test_metadata_aceita_nomes_de_parte_da_interface():
    result = MetadataGenerator({"llm_enabled": False}).generate(
        {"title": "Title"}, "pt", part_number=2, total_parts=3,
        localized_script="Parte localizada.",
    )
    assert (result["part"], result["total_parts"]) == (2, 3)
    assert "Parte 2 de 3" in result["full_description"]


def test_validator_nao_registra_resposta_bruta_nem_valor_invalido(caplog, tmp_path):
    secret = "SECRET_TOKEN_SENTINEL"
    raw = '{"approved":true,"issues":[],"score":"' + secret + '"}'
    result = ValidatorEngine({}, base_dir=tmp_path)._parse_validation_json(raw)
    assert result.status == "unavailable"
    assert secret not in caplog.text
