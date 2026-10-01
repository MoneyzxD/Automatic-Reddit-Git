from pathlib import Path

import pytest

from stages.contextual_glossary import ContextualGlossary, GlossaryIntegrityError


@pytest.fixture
def glossary():
    return ContextualGlossary.from_path(
        Path(__file__).parent.parent / "config" / "contextual_glossary.yaml"
    )


@pytest.mark.parametrize(("source", "target_lang", "expected"), [
    ("Pokemon card", "pt", "carta Pokémon"),
    ("Pokémon card", "pt", "carta Pokémon"),
    ("trading card", "pt", "carta colecionável"),
    ("playing card", "pt", "carta de baralho"),
    ("credit card", "pt", "cartão de crédito"),
    ("birthday card", "pt", "cartão de aniversário"),
    ("business card", "pt", "cartão de visita"),
    ("Pokemon card", "es", "carta Pokémon"),
    ("credit card", "es", "tarjeta de crédito"),
])
def test_glossario_protege_e_restaura_conceito(source, target_lang, expected, glossary):
    protected = glossary.prepare(source, "en", target_lang)
    assert protected.text.isascii()
    assert glossary.restore(protected.text, protected) == expected


def test_longest_match_preserva_conceitos_distintos(glossary):
    protected = glossary.prepare("Pokemon card and credit card", "en", "pt")
    assert len(protected.tokens) == 2
    assert glossary.restore(protected.text, protected) == "carta Pokémon and cartão de crédito"


def test_card_isolado_bloqueia_sem_substituicao_cega(glossary):
    with pytest.raises(GlossaryIntegrityError, match="card"):
        glossary.prepare("I found a card.", "en", "pt")


@pytest.mark.parametrize("change", [lambda token: "", lambda token: token + token,
                                     lambda token: token.replace("ZXQ", "ZZQ", 1)])
def test_token_perdido_duplicado_ou_alterado_bloqueia(glossary, change):
    protected = glossary.prepare("Pokemon card", "en", "pt")
    token = next(iter(protected.tokens))
    with pytest.raises(GlossaryIntegrityError):
        glossary.restore(change(token), protected)
