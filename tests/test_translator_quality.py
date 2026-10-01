import hashlib
import json
from pathlib import Path

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


@pytest.mark.parametrize("target", ["pt", "es"])
@pytest.mark.parametrize("candidate", [
    "I went to the store!", "i went to the store.", "I  went   to the store. ",
])
def test_pontuacao_diferente_nao_disfarca_ingles_inalterado(monkeypatch, target, candidate):
    translator = translator_with(monkeypatch, lambda *_: candidate)
    result = translator.translate("I went to the store.", "en", target)
    assert result.status == "rejected"
    assert result.text is None


def test_ingles_quase_inteiro_com_uma_palavra_trocada_reprova(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "I went to the shop.")
    assert translator.translate("I went to the store.", "en", "pt").status == "rejected"


def test_ingles_residual_sem_marcadores_frequentes_reprova(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "Helen drove home fast.")
    assert translator.translate("Helen drove home quickly.", "en", "pt").status == "rejected"


@pytest.mark.parametrize(("source", "candidate"), [
    ("Helen drove home quickly.", "Well Helen drove home quickly."),
    ("Helen drove home quickly.", "Quickly home drove Helen."),
    ("The story.", "Well The story."),
])
def test_insercao_nao_disfarca_ingles_residual(monkeypatch, source, candidate):
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate(source, "en", "pt").status == "rejected"


@pytest.mark.parametrize(("target", "candidate"), [
    ("pt", "O livro se chamava The End."),
    ("es", "El libro se llamaba The End."),
])
def test_titulo_ingles_preservado_nao_bloqueia_traducao(monkeypatch, target, candidate):
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate("The book was named The End.", "en", target).require_text() == candidate


def test_titulo_ingles_longo_preservado_nao_bloqueia_traducao(monkeypatch):
    candidate = "O livro se chamava The Lord of the Rings."
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate("The book was named The Lord of the Rings.", "en", "pt").require_text() == candidate


def test_nomes_proprios_preservados_com_conjuncao_traduzida(monkeypatch):
    candidate = "Alice Bob Carol e Dave"
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate("Alice Bob Carol Dave", "en", "pt").require_text() == candidate


def test_titulo_composto_ingles_preservado_nao_conta_como_corpo(monkeypatch):
    candidate = "Li The End and The Beginning."
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate("I read The End and The Beginning.", "en", "pt").require_text() == candidate


def test_nomes_compostos_reordenados_nao_contam_como_ingles_residual(monkeypatch):
    candidate = "Mary Jones e John Smith"
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate("John Smith and Mary Jones", "en", "pt").require_text() == candidate


def test_nome_preservado_nao_mascara_corpo_ingles_residual(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "John Smith drove home fast.")
    assert translator.translate("John Smith drove home quickly.", "en", "pt").status == "rejected"


@pytest.mark.parametrize("target", ["pt", "es"])
def test_detector_reprova_ingles_diferente_da_fonte(monkeypatch, target):
    translator = translator_with(monkeypatch, lambda *_: "They walked into a shop.")
    result = translator.translate("My neighbor lost his wallet yesterday.", "en", target)
    assert result.status == "rejected"
    assert result.text is None


def test_nomes_reordenados_nao_escondem_corpo_ingles_parcial(monkeypatch):
    candidate = "Mary Jones e John Smith drove home fast."
    translator = translator_with(monkeypatch, lambda *_: candidate)
    assert translator.translate(
        "John Smith and Mary Jones drove home quickly.", "en", "pt"
    ).status == "rejected"


@pytest.mark.parametrize("target", ["pt", "es"])
def test_titulo_preservado_nao_autoriza_verbo_ingles_trocado(monkeypatch, target):
    translator = translator_with(monkeypatch, lambda *_: "I saw The End.")
    assert translator.translate("I read The End.", "en", target).status == "rejected"
    assert not translator._cached_text_valid("I read The End.", "I saw The End.", "en", target)


@pytest.mark.parametrize(("source", "target", "candidate"), [
    ("The hotel.", "pt", "O hotel."),
    ("The hospital.", "es", "El hospital."),
])
@pytest.mark.parametrize("path", ["translate", "title", "cache"])
def test_cognato_curto_com_artigo_traduzido_e_aprovado(
    monkeypatch, tmp_path, source, target, candidate, path,
):
    translator = translator_with(monkeypatch, lambda *_: candidate)
    if path == "translate":
        assert translator.translate(source, "en", target).require_text() == candidate
    elif path == "title":
        assert translator.translate_title(source, "en", target) == candidate
    else:
        lang_dir = tmp_path / target
        lang_dir.mkdir()
        script = lang_dir / f"script_cognato_{target}.txt"
        script.write_text(candidate, encoding="utf-8")
        script.with_suffix(".cache.json").write_text(json.dumps({
            "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
            "source_lang": "en", "target_lang": target,
            "glossary_version": translator.glossary.version,
        }), encoding="utf-8")
        monkeypatch.setattr(translator, "_translate_chunk_google",
                            lambda *_: pytest.fail("cache válido dispensa provedor"))
        result = translator.translate_all(source, "cognato", tmp_path, [target], "en")[target]
        assert result.provider == "cache"
        assert result.require_text() == candidate


def test_the_dog_sem_cue_nao_e_titulo_protegido(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "The Dog correu.")
    assert translator.translate("The Dog ran.", "en", "pt").status == "rejected"


@pytest.mark.parametrize(("target", "candidate"), [
    ("pt", "O livro se chamava The End por Mary Jones e John Smith."),
    ("es", "El libro se llamaba The End por Mary Jones y John Smith."),
])
def test_detector_aceita_corpo_traduzido_com_titulo_e_nomes(monkeypatch, target, candidate):
    translator = translator_with(monkeypatch, lambda *_: candidate)
    source = "The book was named The End by John Smith and Mary Jones."
    assert translator.translate(source, "en", target).require_text() == candidate


def test_corpo_curto_pt_nao_e_bloqueado_por_detector_frances(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "Fui à loja.")
    assert translator.translate("I went to the store.", "en", "pt").require_text() == "Fui à loja."


def test_detector_indisponivel_bloqueia_corpo_com_evidencia(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "They walked into a shop.")

    def unavailable(*_):
        raise ImportError("langdetect ausente")

    monkeypatch.setattr(translator, "_detect_target_language", unavailable, raising=False)
    result = translator.translate("My neighbor lost his wallet yesterday.", "en", "pt")
    assert result.status == "unavailable"
    assert result.text is None


def test_detector_sem_features_em_corpo_elegivel_falha_fechado(monkeypatch):
    import langdetect

    translator = translator_with(monkeypatch, lambda *_: "They walked into a shop.")
    monkeypatch.setattr(langdetect, "detect_langs", lambda *_: [])
    result = translator.translate("My neighbor lost his wallet yesterday.", "en", "pt")
    assert result.status == "unavailable"
    assert result.text is None


def test_sem_features_dispensa_detector(monkeypatch):
    translator = translator_with(monkeypatch, lambda text, *_: text)
    monkeypatch.setattr(translator, "_detect_target_language",
                        lambda *_: pytest.fail("detector não deve ser chamado"), raising=False)
    assert translator.translate("Pokemon card", "en", "pt").require_text() == "carta Pokémon"


def test_detector_offline_e_deterministico():
    translator = ScriptTranslator({"delay": 0, "retry_waits": [0, 0]})
    results = [translator._detect_target_language("They walked into a shop.") for _ in range(4)]
    assert results == [results[0]] * 4


def test_dependencia_detector_esta_no_manifesto():
    requirements = (Path(__file__).parent.parent / "requirements.txt").read_text(encoding="utf-8")
    assert "langdetect>=1.0.9" in requirements


def test_corpo_curto_ingles_residual_reprova_apesar_de_artigo_traduzido(monkeypatch):
    translator = translator_with(monkeypatch, lambda *_: "O dog ran.")
    result = translator.translate("The dog ran.", "en", "pt")
    assert result.status == "rejected"
    assert result.text is None


@pytest.mark.parametrize(("source", "limit", "expected"), [
    ("bread and", 6, "pão e"),
    ("bread\n\nand", 7, "pão\n\ne"),
])
def test_separadores_de_chunks_sobrevivem_provedor_que_remove_espacos(
    monkeypatch, source, limit, expected,
):
    translator = translator_with(monkeypatch, lambda chunk, *_: "pão" if "bread" in chunk else "e")
    monkeypatch.setattr(translator, "MYMEMORY_CHUNK_SIZE", limit)
    assert translator.translate(source, "en", "pt").require_text() == expected


def test_sentinela_na_fronteira_nunca_e_partida(monkeypatch):
    translator = translator_with(monkeypatch, lambda chunk, *_: chunk.replace("bread", "pão"))
    monkeypatch.setattr(translator, "MYMEMORY_CHUNK_SIZE", 18)
    protected = translator.glossary.prepare("bread Pokemon card", "en", "pt")
    chunks = translator._split_chunks(protected.text, chunk_size=18)
    token = next(iter(protected.tokens))
    assert sum(token in chunk for chunk in chunks) == 1
    assert "".join(chunks) == protected.text
    assert translator.translate("bread Pokemon card", "en", "pt").require_text() == "pão carta Pokémon"


def test_sentinela_em_texto_longo_respeita_limite_mymemory(monkeypatch):
    source = "x" * 440 + "(Pokemon card)" + "y" * 460
    translator = translator_with(monkeypatch, lambda *_: None)
    protected = translator.glossary.prepare(source, "en", "pt")
    token = next(iter(protected.tokens))
    chunks = translator._split_chunks(protected.text, chunk_size=450)
    assert "".join(chunks).encode("utf-8") == protected.text.encode("utf-8")
    assert all(len(chunk) <= 450 for chunk in chunks)
    assert sum(token in chunk for chunk in chunks) == 1

    calls = []

    def memory(chunk, *_):
        calls.append(len(chunk))
        assert len(chunk) <= 450
        return "Texto " + token if token in chunk else "Texto."

    monkeypatch.setattr(translator, "_translate_chunk_mymemory", memory)
    assert translator.translate(source, "en", "pt").status == "approved"
    assert calls


def test_google_invalido_na_primeira_rodada_pode_aprovar_na_segunda(monkeypatch):
    calls = []

    def google(*_):
        calls.append(1)
        return "" if len(calls) == 1 else "Fui à loja."

    translator = translator_with(monkeypatch, google)
    assert translator.translate("I went to the store.", "en", "pt").require_text() == "Fui à loja."
    assert len(calls) == 2


def test_retries_respeitam_ordem_e_param_apos_sucesso(monkeypatch):
    calls = []
    translator = translator_with(monkeypatch, lambda *_: None)

    def google(*_):
        calls.append("Google")
        return None

    def memory(*_):
        calls.append("MyMemory")
        return None

    monkeypatch.setattr(translator, "_translate_chunk_google", google)
    monkeypatch.setattr(translator, "_translate_chunk_mymemory", memory)
    assert translator.translate("The story.", "en", "pt").status == "unavailable"
    assert calls == ["Google", "MyMemory"] * 3

    calls.clear()

    def google_succeeds(*_):
        calls.append("Google")
        return "A história."

    monkeypatch.setattr(translator, "_translate_chunk_google", google_succeeds)
    assert translator.translate("The story.", "en", "pt").require_text() == "A história."
    assert calls == ["Google"]


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


def test_force_ignora_cache_valido(monkeypatch, tmp_path):
    calls = []

    def google(*_):
        calls.append(1)
        return "Texto traduzido."

    translator = translator_with(monkeypatch, google)
    translator.translate_all("The source.", "s4", tmp_path, ["pt"], "en")
    translator.translate_all("The source.", "s4", tmp_path, ["pt"], "en", force=True)
    assert len(calls) == 2


@pytest.mark.parametrize("source_lang,target_lang", [("en", "pt"), ("pt", "pt")])
def test_fonte_vazia_rejeitada_sem_arquivos(monkeypatch, tmp_path, source_lang, target_lang):
    translator = translator_with(monkeypatch, lambda *_: pytest.fail("provedor não deve ser chamado"))
    with pytest.raises(TranslationFailed) as failure:
        translator.translate_all("  \n\t", "s5", tmp_path, [target_lang], source_lang)
    assert failure.value.result.status == "rejected"
    assert not list(tmp_path.rglob("script_s5_*"))


def test_fonte_vazia_nao_reaproveita_cache_antigo(monkeypatch, tmp_path):
    translator = translator_with(monkeypatch, lambda *_: pytest.fail("provedor não deve ser chamado"))
    script_dir = tmp_path / "pt"
    script_dir.mkdir()
    (script_dir / "script_s6_pt.txt").write_text("Texto antigo.", encoding="utf-8")
    (script_dir / "script_s6_pt.cache.json").write_text(json.dumps({
        "source_sha256": hashlib.sha256("  ".encode("utf-8")).hexdigest(),
        "source_lang": "en", "target_lang": "pt", "glossary_version": translator.glossary.version,
    }), encoding="utf-8")
    with pytest.raises(TranslationFailed) as failure:
        translator.translate_all("  ", "s6", tmp_path, ["pt"], "en")
    assert failure.value.result.status == "rejected"


@pytest.mark.parametrize("provider_output", ["Fui à loja.", None])
def test_cache_legado_em_ingles_e_revalidado(monkeypatch, tmp_path, provider_output):
    translator = translator_with(monkeypatch, lambda *_: provider_output)
    script_dir = tmp_path / "pt"
    script_dir.mkdir()
    script = script_dir / "script_s7_pt.txt"
    cache = script.with_suffix(".cache.json")
    script.write_text("I went to the store!", encoding="utf-8")
    metadata = {
        "source_sha256": hashlib.sha256("I went to the store.".encode("utf-8")).hexdigest(),
        "source_lang": "en", "target_lang": "pt", "glossary_version": translator.glossary.version,
    }
    cache.write_text(json.dumps(metadata), encoding="utf-8")
    if provider_output is None:
        with pytest.raises(TranslationFailed):
            translator.translate_all("I went to the store.", "s7", tmp_path, ["pt"], "en")
        assert script.read_text(encoding="utf-8") == "I went to the store!"
        assert json.loads(cache.read_text(encoding="utf-8")) == metadata
    else:
        result = translator.translate_all("I went to the store.", "s7", tmp_path, ["pt"], "en")["pt"]
        assert result.provider != "cache"
        assert result.require_text() == provider_output
        assert script.read_text(encoding="utf-8") == provider_output


@pytest.mark.parametrize("provider_output", ["O cachorro correu.", None])
def test_cache_legado_com_corpo_ingles_curto_e_revalidado(monkeypatch, tmp_path, provider_output):
    translator = translator_with(monkeypatch, lambda *_: provider_output)
    script_dir = tmp_path / "pt"
    script_dir.mkdir()
    script = script_dir / "script_s8_pt.txt"
    cache = script.with_suffix(".cache.json")
    script.write_text("O dog ran.", encoding="utf-8")
    metadata = {
        "source_sha256": hashlib.sha256("The dog ran.".encode("utf-8")).hexdigest(),
        "source_lang": "en", "target_lang": "pt", "glossary_version": translator.glossary.version,
    }
    cache.write_text(json.dumps(metadata), encoding="utf-8")
    if provider_output is None:
        with pytest.raises(TranslationFailed):
            translator.translate_all("The dog ran.", "s8", tmp_path, ["pt"], "en")
        assert script.read_text(encoding="utf-8") == "O dog ran."
        assert json.loads(cache.read_text(encoding="utf-8")) == metadata
    else:
        result = translator.translate_all("The dog ran.", "s8", tmp_path, ["pt"], "en")["pt"]
        assert result.provider != "cache"
        assert result.require_text() == provider_output


@pytest.mark.parametrize("target", ["pt", "es"])
def test_cache_legado_ingles_diferente_da_fonte_nao_e_aprovado(monkeypatch, tmp_path, target):
    translator = translator_with(monkeypatch, lambda *_: None)
    lang_dir = tmp_path / target
    lang_dir.mkdir()
    script = lang_dir / f"script_s9_{target}.txt"
    cache = script.with_suffix(".cache.json")
    source = "My neighbor lost his wallet yesterday."
    script.write_text("They walked into a shop.", encoding="utf-8")
    metadata = {
        "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
        "source_lang": "en", "target_lang": target,
        "glossary_version": translator.glossary.version,
    }
    cache.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(TranslationFailed):
        translator.translate_all(source, "s9", tmp_path, [target], "en")
    assert script.read_text(encoding="utf-8") == "They walked into a shop."
    assert json.loads(cache.read_text(encoding="utf-8")) == metadata
