import pytest

from stages.metadata import MetadataGenerator


@pytest.mark.parametrize("length", [92, 93, 100])
def test_youtube_preserva_titulo_e_so_acrescenta_hashtag_se_couber(length):
    hook = "a" * (length - 1) + "?"

    block = MetadataGenerator({"llm_enabled": False})._build_youtube_block(
        hook, "Description", ["#shorts"], "en",
    )

    assert block["title"] == (hook + " #shorts" if length <= 92 else hook)
    assert len(block["title"]) <= 100


def test_youtube_rejeita_hook_excedido_sem_cortar_texto_aprovado():
    hook = (
        "I stopped giving my son fifteen thousand dollars after learning his wife never had surgery, "
        "and now everyone thinks I"
    )

    with pytest.raises(ValueError, match="100"):
        MetadataGenerator({"llm_enabled": False})._build_youtube_block(
            hook, "Description", [], "en",
        )


def test_rebuild_rejeita_hook_excedido_antes_de_modificar_metadados():
    metadata = {"language": "en", "hook": "x" * 101, "description": "Texto aprovado"}
    before = metadata.copy()

    with pytest.raises(ValueError, match="100"):
        MetadataGenerator({"llm_enabled": False}).rebuild_after_validation(
            metadata, "Nova descrição", [],
        )

    assert metadata == before
