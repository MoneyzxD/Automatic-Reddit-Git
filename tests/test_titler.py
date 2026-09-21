import re

from stages.titler import TitleGenerator, normalize_title_sentence
from stages.validator import ValidationResult, ValidatorEngine


SEPARADOR_DE_ORACOES = re.compile(r"\s[-–—]\s")


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
        lambda *args, **kwargs: ValidationResult(approved=True, score=100),
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
