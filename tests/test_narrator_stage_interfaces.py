from types import SimpleNamespace

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
