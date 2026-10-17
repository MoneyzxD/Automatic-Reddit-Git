import re
from types import SimpleNamespace

import pytest

from stages.titler import TitleGenerator, normalize_title_sentence
from stages.validator import ValidationResult, ValidatorEngine


SEPARADOR_DE_ORACOES = re.compile(r"\s[-–—]\s")
HOOK_LONGO_EN = (
    "I stopped giving my son fifteen thousand dollars after learning his wife never had surgery, "
    "and now everyone thinks I am wrong."
)


@pytest.mark.parametrize("method", ["_groq_title", "_groq_hook", "_groq_closing"])
def test_texto_publico_reserva_tokens_para_raciocinio_sem_cair_em_fallback(method, monkeypatch):
    from utils import environment, llm_client

    monkeypatch.setattr(environment, "llm_api_key", lambda *args: "chave-teste")
    calls = []

    def complete(**kwargs):
        calls.append(kwargs)
        # Incidente 1wybqga: o raciocínio consumiu os 400 tokens disponíveis.
        suficiente = kwargs["max_tokens"] >= 2048
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop" if suficiente else "length",
            message=SimpleNamespace(content="I refused to pay." if suficiente else ""),
        )])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(llm_client, "tracked_llm", lambda *args: client)

    assert getattr(TitleGenerator({}), method)("Title", "Story", "en") == "I refused to pay."
    assert len(calls) == 1
    assert calls[0]["max_tokens"] == 2048


def test_clean_hook_longo_nao_corta_frase_do_incidente():
    generator = TitleGenerator({})

    assert generator._clean_title(HOOK_LONGO_EN, is_hook=True, language="en") == ""


@pytest.mark.parametrize("text", ["I found out: the surgery never happened.", "I found out\nwhat really happened."])
def test_clean_title_nao_descarta_continuacao(text):
    assert TitleGenerator({})._clean_title(text, language="en") == ""


@pytest.mark.parametrize("text", ["I refused to pay.", "Was I wrong to refuse?"])
def test_clean_title_preserva_pontuacao_final(text):
    assert TitleGenerator({})._clean_title(text, language="en") == text


@pytest.mark.parametrize("provider", ["groq", "ollama"])
def test_provedor_rejeita_hook_acima_do_limite_youtube_sem_nova_tentativa(provider, monkeypatch):
    from utils import environment, groq_client

    response = HOOK_LONGO_EN[:117]
    calls = []
    monkeypatch.setattr(environment, "groq_api_key", lambda lang: "chave-teste")

    def complete(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop", message=SimpleNamespace(content=response),
        )])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=complete)))
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: client)

    def post(url, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(status_code=200, json=lambda: {"response": response})

    monkeypatch.setattr("requests.post", post)
    result = getattr(TitleGenerator({}), f"_{provider}_hook")("Title", "Story", "en")

    assert result is None
    assert len(calls) == 1


@pytest.mark.parametrize("enabled", [True, False])
def test_hook_fallback_longo_interrompe_sem_inventar_titulo(enabled, monkeypatch):
    generator = TitleGenerator({"enabled": enabled})
    monkeypatch.setattr(generator, "_groq_hook", lambda *args: None)
    monkeypatch.setattr(generator, "_ollama_hook", lambda *args: None)

    with pytest.raises(ValueError, match="100"):
        generator.generate_hook("Story", "en", HOOK_LONGO_EN)


def test_fallback_preserva_frase_inteira_decimal_e_interrogacao():
    title = "Was I wrong to ask for $15.50 back?"

    assert TitleGenerator({"enabled": False}).generate_hook(
        "Story", "en", "AITA " + title,
    ) == title


@pytest.mark.parametrize("language", ["pt", "en", "es"])
def test_prompt_hook_pede_limite_do_titulo_youtube(language):
    from stages.titler import HOOK_PROMPTS

    assert "100" in HOOK_PROMPTS[language]
    assert "120" not in HOOK_PROMPTS[language]


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
