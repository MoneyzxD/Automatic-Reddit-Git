import re
from types import SimpleNamespace

import pytest

from stages.titler import TitleGenerator, normalize_title_sentence
from stages.validator import ValidationResult, ValidatorEngine


SEPARADOR_DE_ORACOES = re.compile(r"\s[-–—]\s")


@pytest.mark.parametrize("provider", ["groq", "ollama"])
@pytest.mark.parametrize("gender", ["male", "female"])
@pytest.mark.parametrize("language", ["pt", "es"])
def test_hook_nao_impoe_genero_dos_exemplos_ao_narrador(
    provider, gender, language, monkeypatch,
):
    from utils import environment, groq_client

    prompts = []
    response = "Errei ao cortar meu filho?" if language == "pt" else "¿Estuve mal por cortar a mi hijo?"
    monkeypatch.setattr(
        environment, "groq_api_key",
        lambda lang: "chave-teste" if provider == "groq" else "",
    )

    def complete(**kwargs):
        prompts.append(kwargs["messages"][1]["content"])
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=response),
        )])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)

    def post(url, **kwargs):
        prompts.append(kwargs["json"]["prompt"])
        return SimpleNamespace(status_code=200, json=lambda: {"response": response})

    monkeypatch.setattr("requests.post", post)
    generator = TitleGenerator({})
    generator.groq_key = ""
    parent = "papá" if gender == "male" else "mamá"
    dialogue = 'Mi hermana dijo: "¿Soy la mala de la historia?"'
    context = (
        f"Tengo 52 años y soy su {parent}. "
        + "Pedía dinero para una cirugía. " * 300
        + f"La supuesta cirugía nunca ocurrió. {dialogue}"
    )

    assert generator.generate_hook(
        context, language, "Una supuesta cirugía", narrator_gender=gender,
        factual_context=context,
    ) == response

    assert len(prompts) == 1
    prompt = prompts[0]
    assert context in prompt
    assert f"NARRADOR: {gender}" in prompt
    # O trecho da fonte pode ter falas femininas; só os exemplos fixos são neutros.
    examples = prompt.split("TIPOS DE HOOK", 1)[1]
    for form in ("Estou errada", "vilã", "enfermeira", "la mala", "la villana"):
        assert form not in examples
    assert "mi hermana" in examples or "minha irmã" in examples
    assert "NARRADOR" in examples
    assert "male = masculino" in examples
    assert f"female = {'feminino' if language == 'pt' else 'femenino'}" in examples


def test_clean_hook_conecta_oracoes_sem_hifen():
    hook = (
        "Recusei deixar o namorado da minha colega na minha casa e ele não "
        "paga nada - agora estou em guerra com ela."
    )

    resultado = TitleGenerator({})._clean_title(
        hook,
        is_hook=True,
        language="pt",
    )

    assert not SEPARADOR_DE_ORACOES.search(resultado)
    assert resultado.endswith("ele não paga nada e agora estou em guerra com ela.")


def test_normalizacao_preserva_hifen_interno_de_palavra():
    titulo = "My 79-year-old neighbor complained — now everyone knows"

    resultado = normalize_title_sentence(titulo, "en")

    assert "79-year-old" in resultado
    assert resultado.endswith("complained and now everyone knows")


def test_validacao_aprovada_nao_deixa_separador_escapar(monkeypatch, tmp_path):
    validador = ValidatorEngine({}, base_dir=tmp_path)
    monkeypatch.setattr(
        validador,
        "validate_title_hook",
        lambda *args, **kwargs: ValidationResult(status="approved", approved=True, score=100),
    )
    monkeypatch.setattr(validador, "log_attempt", lambda *args, **kwargs: None)

    titulo, hook = validador.validate_and_fix_title_hook(
        "Conflito familiar - uma decisão difícil",
        "Recusei o pedido - agora minha colega está furiosa comigo.",
        story_text="Uma colega pediu para o namorado morar de graça na casa da narradora.",
        language="pt",
        story_id="teste",
    )

    assert not SEPARADOR_DE_ORACOES.search(titulo)
    assert not SEPARADOR_DE_ORACOES.search(hook)
