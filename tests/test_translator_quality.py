import json

import pytest

from stages.translator import ScriptTranslator, TranslationFailed, TranslationResult


def translator_with(monkeypatch, google, memory=None):
    translator = ScriptTranslator({"delay": 0, "retry_waits": [0, 0]})
    monkeypatch.setattr(translator, "_translate_chunk_google", google)
    monkeypatch.setattr(translator, "_translate_chunk_mymemory", memory or (lambda *_: None))
    return translator


def test_um_chunk_vazio_reprova_traducao_inteira(monkeypatch):
    translator = translator_with(monkeypatch, lambda text, *_: "um" if text.strip() == "one" else "")
    monkeypatch.setattr(translator, "_split_chunks", lambda text, chunk_size=None: ["one", "two"])
    result = translator.translate("one two", "en", "pt")
    assert result.status == "rejected"
    assert result.text is None
    assert len(result.chunks) == 2


def test_falha_nunca_devolve_ingles_como_portugues(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: None)
    result = translator.translate("This stayed English.", "en", "pt")
    assert result.status == "unavailable"
    assert result.text is None
    with pytest.raises(TranslationFailed):
        result.require_text()


def test_placeholder_perdido_reprova_traducao(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "Troquei alguma coisa")
    result = translator.translate("I traded a Pokemon card", "en", "pt")
    assert result.status == "rejected"
    assert "placeholder" in result.error.lower()


def test_termo_contextual_e_restauração_integral(monkeypatch):
    translator = translator_with(monkeypatch, lambda text, *_: text.replace("I bought a", "Comprei uma"))
    result = translator.translate("I bought a Pokemon card", "en", "pt")
    assert result.require_text() == "Comprei uma carta Pokémon"
    assert result.chunks[0].provider == "Google"


def test_termo_isolado_pode_ser_aprovado_com_sentinela_preservada(monkeypatch):
    translator = translator_with(monkeypatch, lambda text, *_: text)
    result = translator.translate("Pokemon card", "en", "pt")
    assert result.require_text() == "carta Pokémon"


def test_card_ambiguo_reprova_sem_chamar_provedor(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: pytest.fail("provedor não deve ser chamado"))
    result = translator.translate("I found a card.", "en", "pt")
    assert result.status == "rejected"
    assert result.text is None


def test_texto_inalterado_reprova_e_fallback_pode_aprovar(monkeypatch):
    translator = translator_with(monkeypatch, lambda text, *_: text,
                                 lambda text, *_: "Isso mudou.")
    assert translator.translate("This changed.", "en", "pt").require_text() == "Isso mudou."


def test_ingles_residual_reprova_idioma_alvo(monkeypatch):
    source = "The woman and the man were with the family in the house."
    translator = translator_with(monkeypatch, lambda *_: source.replace("house", "home"))
    result = translator.translate(source, "en", "pt")
    assert result.status == "rejected"
    assert result.text is None


def test_cache_exige_fonte_idiomas_e_versao_e_só_grava_aprovado(monkeypatch, tmp_path):
    calls = []

    def google(text, *_):
        calls.append(text)
        return "Texto traduzido."

    translator = translator_with(monkeypatch, google)
    first = translator.translate_all("Original text.", "s1", tmp_path, ["pt"], "en")
    assert isinstance(first["pt"], TranslationResult)
    assert first["pt"].require_text() == "Texto traduzido."
    script = tmp_path / "pt" / "script_s1_pt.txt"
    cache = script.with_suffix(".cache.json")
    metadata = json.loads(cache.read_text(encoding="utf-8"))
    assert set(metadata) == {"source_sha256", "source_lang", "target_lang", "glossary_version"}
    assert len(metadata["source_sha256"]) == 64
    assert len(calls) == 1
    translator.translate_all("Original text.", "s1", tmp_path, ["pt"], "en")
    assert len(calls) == 1
    translator.translate_all("Changed text.", "s1", tmp_path, ["pt"], "en")
    assert len(calls) == 2
    translator.glossary.version = "2"
    translator.translate_all("Changed text.", "s1", tmp_path, ["pt"], "en")
    assert len(calls) == 3
    monkeypatch.setattr(translator, "_translate_chunk_google", lambda *_: None)
    with pytest.raises(TranslationFailed):
        translator.translate_all("Failed text.", "s1", tmp_path, ["pt"], "en")
    assert script.read_text(encoding="utf-8") == "Texto traduzido."
    assert json.loads(cache.read_text(encoding="utf-8"))["glossary_version"] == "2"


def test_titulo_falho_levanta_excecao(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: None)
    with pytest.raises(TranslationFailed):
        translator.translate_title("The story", "en", "pt")


@pytest.mark.parametrize("provider_output,status", [(None, "unavailable"), ("", "rejected")])
def test_resultado_nao_aprovado_nao_cria_arquivos(monkeypatch, tmp_path, provider_output, status):
    translator = translator_with(monkeypatch, lambda *_: provider_output)
    with pytest.raises(TranslationFailed) as failure:
        translator.translate_all("The source.", "s2", tmp_path, ["pt"], "en")
    assert failure.value.result.status == status
    assert not (tmp_path / "pt" / "script_s2_pt.txt").exists()
    assert not (tmp_path / "pt" / "script_s2_pt.cache.json").exists()


def test_cache_com_idioma_fonte_ou_alvo_divergente_retraduz(monkeypatch, tmp_path):
    calls = []

    def google(*_):
        calls.append(1)
        return "Texto traduzido."

    translator = translator_with(monkeypatch, google)
    translator.translate_all("The source.", "s3", tmp_path, ["pt"], "en")
    cache = tmp_path / "pt" / "script_s3_pt.cache.json"
    for field, value in (("source_lang", "es"), ("target_lang", "es")):
        metadata = json.loads(cache.read_text(encoding="utf-8"))
        metadata[field] = value
        cache.write_text(json.dumps(metadata), encoding="utf-8")
        translator.translate_all("The source.", "s3", tmp_path, ["pt"], "en")
    assert len(calls) == 3
