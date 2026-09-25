import pytest

from utils.text_chunks import join_lossless, split_lossless


def test_chunks_preservam_cada_caractere_e_offsets():
    texto = "Inicio.\n\n" + ("paragrafo longo com acao. " * 40) + "I (44M) no fim."
    chunks = split_lossless(texto, max_chars=120)

    assert join_lossless(chunks) == texto
    assert "".join(c.text for c in chunks) == texto
    assert all(texto[c.start:c.end] == c.text for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert [c.start for c in chunks] == [0] + [c.end for c in chunks[:-1]]
    assert all(0 < len(c.text) <= 120 for c in chunks)
    assert "I (44M)" in chunks[-1].text


def test_chunks_nao_quebram_unicode_nem_emoji():
    texto = "Joao disse: olá 👨‍👨‍👦. Depois, Pokémon apareceu."
    chunks = split_lossless(texto, max_chars=18)

    assert join_lossless(chunks) == texto
    assert all(texto[c.start:c.end] == c.text for c in chunks)
    assert all(len(c.text) <= 18 for c in chunks)


def test_chunks_respeitam_limite_ao_cortar_em_pontuacao():
    texto = "a" * 31 + ". " + "b" * 40
    chunks = split_lossless(texto, max_chars=32)

    assert join_lossless(chunks) == texto
    assert all(len(c.text) <= 32 for c in chunks)


def test_texto_vazio_nao_produz_chunks():
    assert split_lossless("", max_chars=1) == []
    assert join_lossless([]) == ""


def test_limite_nao_positivo_e_rejeitado():
    with pytest.raises(ValueError, match="max_chars"):
        split_lossless("texto", max_chars=0)
