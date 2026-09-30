from types import SimpleNamespace
import json

import pytest

from stages.titler import TitleGenerator
from stages.metadata import MetadataGenerator
from stages.validator import ValidatorEngine


@pytest.mark.parametrize("method", ["generate", "generate_hook", "generate_closing_hook"])
@pytest.mark.parametrize("provider", ["groq", "ollama"])
def test_titulos_enviam_genero_travado_aos_provedores(method, provider, monkeypatch):
    from utils import environment, groq_client
    prompts = []
    monkeypatch.setattr(environment, "groq_api_key", lambda lang: "chave-teste" if provider == "groq" else "")

    def complete(**kwargs):
        prompts.append(kwargs["messages"][1]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Uma historia familiar."))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)

    def post(url, **kwargs):
        prompts.append(kwargs["json"]["prompt"])
        return SimpleNamespace(status_code=200, json=lambda: {"response": "Uma historia familiar."})

    monkeypatch.setattr("requests.post", post)
    generator = TitleGenerator({})
    generator.groq_key = ""
    result = getattr(generator, method)("Contexto. " * 100, "pt", "Titulo", narrator_gender="male")
    assert result
    assert len(prompts) == 1
    assert "NARRADOR: male" in prompts[0]


@pytest.mark.parametrize("method", ["generate", "generate_hook", "generate_closing_hook"])
def test_titulos_rejeitam_genero_invalido_mesmo_sem_llm(method):
    with pytest.raises(ValueError, match="male ou female"):
        getattr(TitleGenerator({"enabled": False}), method)("Texto", narrator_gender="unknown")


def test_validacao_metadados_propaga_genero_ate_correcao(monkeypatch, tmp_path):
    engine = ValidatorEngine({}, base_dir=tmp_path)
    prompts = []
    responses = iter([
        '{"approved":false,"score":40,"issues":[{"trecho":"description","problema":"Concordancia","sugestao":"Reescreva a descricao"}]}',
        "Fiquei cansado de discutir.",
        '{"approved":true,"score":100,"issues":[]}',
    ])

    def call(**kwargs):
        prompts.append(kwargs["user_prompt"])
        return next(responses)

    monkeypatch.setattr(engine, "_call_groq", call)
    desc, tags = engine.validate_and_fix_metadata(
        "Fiquei cansada.", [], "Contexto", "pt", "story", narrator_gender="male")
    assert desc == "Fiquei cansado de discutir."
    assert len(prompts) == 3
    assert all("NARRADOR: male" in prompt for prompt in prompts)


def test_metadados_rejeitam_genero_invalido():
    with pytest.raises(ValueError, match="male ou female"):
        MetadataGenerator({"llm_enabled": False}).generate({}, "pt", narrator_gender="unknown")


def test_metadados_preservam_genero_no_resultado(monkeypatch):
    generator = MetadataGenerator({"llm_enabled": False})
    result = generator.generate({"id": "story", "title": "Titulo"}, "pt", narrator_gender="male")
    assert result["narrator_gender"] == "male"


@pytest.mark.parametrize("stage", ["script", "titulo", "hook"])
@pytest.mark.parametrize("gender", ["male", "female"])
def test_validacao_correcao_e_revalidacao_preservam_genero(stage, gender, monkeypatch, tmp_path):
    engine = ValidatorEngine({}, base_dir=tmp_path)
    prompts = []
    corrected = "Fiquei cansado de discutir." if gender == "male" else "Fiquei cansada de discutir."
    issue = {"trecho": "Fiquei confuso." if stage == "script" else stage,
             "problema": "Concordancia do narrador", "sugestao": "Reescreva com concordancia correta"}
    responses = iter([
        json.dumps({"approved": False, "score": 40, "issues": [issue]}),
        corrected,
        '{"approved":true,"score":100,"issues":[]}',
    ])

    def call(**kwargs):
        prompts.append(kwargs["user_prompt"])
        return next(responses)

    monkeypatch.setattr(engine, "_call_groq", call)
    if stage == "script":
        result = engine.validate_and_fix_script("Fiquei confuso.", "pt", gender, "story")
        assert result == corrected
    else:
        title, hook = engine.validate_and_fix_title_hook(
            "Titulo original", "Hook original", "Contexto", "pt", "story", narrator_gender=gender)
        assert (title, hook) == ((corrected, "Hook original") if stage == "titulo"
                                 else ("Titulo original", corrected))
    assert len(prompts) == 3
    assert [f"NARRADOR: {gender}" in prompt for prompt in prompts] == [True, True, True]


@pytest.mark.parametrize("invalid", ["unknown", "", "other"])
@pytest.mark.parametrize("stage", ["script", "titulo"])
def test_correcao_rejeita_genero_invalido_antes_de_qualquer_trabalho(stage, invalid, tmp_path):
    engine = ValidatorEngine({}, base_dir=tmp_path)
    with pytest.raises(ValueError, match="male ou female"):
        if stage == "script":
            engine.apply_surgical_fix("Texto", [], narrator_gender=invalid)
        else:
            engine.apply_title_hook_fix("Titulo", "Hook", [], "Texto", narrator_gender=invalid)


def test_correcao_titulo_preserva_chamada_legada_sem_genero(monkeypatch, tmp_path):
    engine = ValidatorEngine({}, base_dir=tmp_path)
    prompts = []
    responses = iter([
        '{"approved":false,"score":40,"issues":[{"trecho":"titulo","problema":"Clareza","sugestao":"Reescreva o titulo"}]}',
        "Uma decisao familiar",
        '{"approved":true,"score":100,"issues":[]}',
    ])

    def call(**kwargs):
        prompts.append(kwargs["user_prompt"])
        return next(responses)

    monkeypatch.setattr(engine, "_call_groq", call)
    assert engine.validate_and_fix_title_hook(
        "Titulo", "Hook", "Contexto", "pt", "story") == ("Uma decisao familiar", "Hook")
    assert len(prompts) == 3
    assert all("NARRADOR: None" not in prompt for prompt in prompts)
