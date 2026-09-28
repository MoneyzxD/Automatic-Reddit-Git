import json
from dataclasses import FrozenInstanceError
from types import SimpleNamespace

import pytest

from stages.gender_detector import GenderDetector
from stages.narrator_profile import (
    NarratorEvidence, NarratorProfileResolver, load_profile, save_profile,
)
from utils import telemetry


def resolver_sem_llm(**config):
    return NarratorProfileResolver({"chunk_chars": 256, **config}, semantic_provider=lambda chunk: [])


def resolver_texto(texto, **kwargs):
    return resolver_sem_llm().resolve(story_id="historia", title="Title", original_text=texto, **kwargs)


@pytest.mark.parametrize("texto,genero", [
    ("I (28M) have long hair and live with my husband.", "male"),
    ("I (28F) live with my wife.", "female"),
    ("I, M28, finally answered.", "male"),
    ("I am F28 and live alone.", "female"),
    ("I am a man.", "male"),
    ("I'm a woman.", "female"),
    ("I am a 28-year-old woman.", "female"),
    ("My sister said, 'I'm a woman.' I (31M) disagreed.", "male"),
    ("No gender clue here. " * 300 + " I (44M) finally answered.", "male"),
])
def test_evidencia_explicita_do_narrador(texto, genero):
    perfil = resolver_texto(texto)
    assert perfil.source_gender == genero
    assert perfil.narration_gender == genero
    fonte = "Title\n\n" + texto
    assert all(fonte[e.start:e.start + len(e.quote)] == e.quote for e in perfil.evidence)


def test_titulo_e_lido_e_regra_nao_depende_do_limite_de_chunk():
    perfil = resolver_sem_llm(chunk_chars=1).resolve(
        story_id="title", title="I (28F) need advice", original_text="No useful clue.",
    )
    assert perfil.narration_gender == "female"


@pytest.mark.parametrize("texto", [
    "My husband is a man. I have long hair and work as a nurse.",
    "My wife (28F) and brother M28 talked.",
    "My sister said, 'I'm a woman.'", 'My brother said, "I am a man."',
    "I am gay. I love dresses, football and my boyfriend. My name is Mary.",
    "I was sad and tired. Eu estava cansada e sou enfermeira.",
])
def test_terceiros_e_estereotipos_tem_peso_zero(texto):
    perfil = resolver_texto(texto)
    assert perfil.source_gender == "unknown"
    assert perfil.decision_method == "stable_tiebreak"
    assert perfil.evidence == ()


def test_empate_e_estavel_binario_e_modelos_sao_imutaveis():
    a = resolver_texto("No useful clue.")
    b = resolver_texto("No useful clue.")
    assert a == b
    assert a.narration_gender in {"male", "female"}
    assert a.decision_method == "stable_tiebreak"
    with pytest.raises(FrozenInstanceError):
        a.narration_gender = "unknown"
    e = resolver_texto("I (28M) answered.").evidence[0]
    with pytest.raises(FrozenInstanceError):
        e.weight = 0


def test_conflito_explicito_nao_inventa_certeza():
    perfil = resolver_texto("I (28F) answered. I (28M) answered.")
    assert perfil.source_gender == "unknown"
    assert perfil.decision_method == "stable_tiebreak"


@pytest.mark.parametrize("quote,subject", [
    ("I am definitely a woman", "narrator"),
    ("Nothing says that.", "sister"),
    ("", "narrator"),
])
def test_citacao_inventada_ou_sujeito_errado_e_descartado(quote, subject):
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", quote, -1, "female", .8, subject, "groq"),
    ])
    perfil = resolver.resolve(story_id="fake", title="Title", original_text="Nothing says that.")
    assert perfil.evidence == ()
    assert perfil.decision_method == "stable_tiebreak"


@pytest.mark.parametrize("texto", [
    "I have a husband.", "I have long hair.", "I am a nurse.", "I am gay.",
    "My sister said, 'I am a woman.'",
])
def test_semantica_nao_pode_pontuar_estereotipo_ou_fala_de_terceiro(texto):
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, "female", 1, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="stereo", title="Title", original_text=texto)
    assert perfil.source_gender == "unknown"
    assert perfil.evidence == ()


def test_semantica_valida_normaliza_confianca_e_offsets():
    texto = "I identify as a woman."
    resolver = NarratorProfileResolver({"chunk_chars": 64}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, " FEMALE ", 9, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="semantic", title="Title", original_text=texto)
    assert perfil.narration_gender == "female"
    assert perfil.decision_method == "semantic"
    assert perfil.evidence[0].start == 7
    assert perfil.evidence[0].weight == 1
    assert perfil.confidence == 1


def test_identidade_depende_so_da_fonte_e_versao():
    entrada = dict(story_id="id", title="Title", original_text="I identify as a woman.")
    sem = resolver_sem_llm().resolve(**entrada)
    com = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", "I identify as a woman.", -1, "female", .9, "narrator", "groq"),
    ]).resolve(**entrada)
    assert sem.profile_id == com.profile_id
    assert sem.source_sha256 == com.source_sha256
    for campo, valor in [("title", "Outro"), ("story_id", "outro"), ("original_text", "Outro")]:
        assert resolver_sem_llm().resolve(**{**entrada, campo: valor}).profile_id != sem.profile_id
    assert resolver_sem_llm(resolver_version="2").resolve(**entrada).profile_id != sem.profile_id


def test_dry_run_nao_chama_provider_nem_persiste(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    def proibido(chunk):
        pytest.fail("Dry-run chamou provider")
    perfil = NarratorProfileResolver({}, semantic_provider=proibido, semantic_enabled=False).resolve(
        story_id="dry", title="Title", original_text="No useful clue.",
    )
    assert perfil.narration_gender in {"male", "female"}
    assert not list(tmp_path.iterdir())


def test_roundtrip_atomico_e_rejeicao_de_sidecar_obsoleto(tmp_path):
    perfil = resolver_texto("I (28M) answered.")
    destino = save_profile(perfil, tmp_path)
    assert destino == tmp_path / "data/scripts/profiles/historia_narrator_profile.json"
    assert load_profile("historia", tmp_path, perfil.source_sha256, "1") == perfil
    assert load_profile("historia", tmp_path, "hash-invalido", "1") is None
    assert load_profile("historia", tmp_path, perfil.source_sha256, "2") is None
    assert list(destino.parent.iterdir()) == [destino]
    assert json.loads(destino.read_text(encoding="utf-8"))["evidence"][0]["gender"] == "male"


def test_sidecar_ausente_ou_corrompido_retorna_none(tmp_path):
    assert load_profile("historia", tmp_path, "hash", "1") is None
    destino = save_profile(resolver_texto("I (28M) answered."), tmp_path)
    destino.write_text("{", encoding="utf-8")
    assert load_profile("historia", tmp_path, "hash", "1") is None


def test_fachada_exige_bind_e_nao_inspeciona_texto(monkeypatch):
    detector = GenderDetector()
    with pytest.raises(RuntimeError, match="Perfil do narrador"):
        detector.detect()
    perfil = resolver_texto("I (28M) answered.")
    detector.bind_profile(perfil)
    class TextoProibido:
        def __str__(self):
            pytest.fail("Fachada inspecionou texto")
    for idioma in ("en", "pt", "es"):
        assert detector.detect(TextoProibido(), idioma) == {
            "narrator_gender": "male", "narrator_confidence": perfil.confidence,
            "corrections_needed": False, "profile_id": perfil.profile_id,
        }


def test_adapter_groq_recebe_todos_chunks_e_json_estrito(monkeypatch):
    from utils import environment, groq_client
    chamadas = []
    def create(**kwargs):
        chamadas.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
            "evidence": [{"quote": "I identify as a woman.", "gender": "female", "confidence": .94,
                          "subject": "narrator", "reason": "first-person self-identification"}],
        })))])
    def cliente(chave, etapa):
        assert (chave, etapa) == ("chave-falsa", "narrator_profile")
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(environment, "groq_api_key", lambda lang: "chave-falsa" if lang == "en" else None)
    monkeypatch.setattr(groq_client, "tracked_groq", cliente)
    texto = "No clue. " * 800 + "I identify as a woman."
    perfil = NarratorProfileResolver({"chunk_chars": 128}).resolve(story_id="groq", title="Title", original_text=texto)
    assert perfil.narration_gender == "female"
    assert "".join(c["messages"][-1]["content"] for c in chamadas) == "Title\n\n" + texto
    assert all(c["temperature"] == 0 and c["response_format"] == {"type": "json_object"} for c in chamadas)


@pytest.mark.parametrize("resposta", ["erro", "json-invalido", "sem-chave"])
def test_falha_groq_registra_telemetria_sem_vazar_segredo(monkeypatch, caplog, resposta):
    from utils import environment, groq_client
    telemetry.reset()
    def create(**kwargs):
        if resposta == "erro":
            raise RuntimeError("SEGREDO-NAO-LOGAR")
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="invalid"))])
    monkeypatch.setattr(environment, "groq_api_key", lambda lang: "" if resposta == "sem-chave" else "fake")
    monkeypatch.setattr(groq_client, "tracked_groq", lambda *args: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
    ))
    perfil = NarratorProfileResolver({}).resolve(story_id="falha", title="Title", original_text="I (28M) answered.")
    assert perfil.narration_gender == "male"
    assert any(f["stage"] == "narrator_profile" for f in telemetry.fallbacks())
    assert "SEGREDO-NAO-LOGAR" not in caplog.text


def test_comparacao_de_terceira_pessoa_nao_e_autoidentificacao():
    texto = "As a woman, my sister understood."
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, "female", 1, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="terceira", title="Title", original_text=texto)
    assert perfil.evidence == ()
    assert perfil.source_gender == "unknown"


@pytest.mark.parametrize("gender,weight,esperado", [
    ("female", -.5, "unknown"), ("female", .69, "unknown"),
    ("female", float("nan"), "unknown"), ("female", float("inf"), "unknown"),
    ("female", "invalido", "unknown"), ("alien", 1, "unknown"),
    ("female", .7, "female"),
])
def test_semantica_respeita_limiar_e_valores_invalidos(gender, weight, esperado):
    texto = "I identify as a woman."
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, gender, weight, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="limiar", title="Title", original_text=texto)
    assert perfil.source_gender == esperado
    assert all(e.gender in {"male", "female", "unknown"} and 0 <= e.weight <= 1 for e in perfil.evidence)


def test_citacao_de_outro_chunk_nao_e_aceita():
    texto = "I identify as a woman. " + "No clue. " * 20
    def provider(chunk):
        if chunk.start == 0:
            return []
        return [NarratorEvidence("semantic", "I identify as a woman.", -1, "female", 1, "narrator", "groq")]
    perfil = NarratorProfileResolver({"chunk_chars": 64}, semantic_provider=provider).resolve(
        story_id="chunk-errado", title="Title", original_text=texto,
    )
    assert perfil.evidence == ()


def test_falha_atomica_preserva_sidecar_anterior(tmp_path, monkeypatch):
    from stages import narrator_profile
    perfil = resolver_texto("I (28M) answered.")
    destino = save_profile(perfil, tmp_path)
    anterior = destino.read_bytes()
    def falha(origem, alvo):
        raise OSError("Falha simulada de substituição")
    monkeypatch.setattr(narrator_profile.os, "replace", falha)
    with pytest.raises(OSError):
        save_profile(resolver_texto("I (28F) answered."), tmp_path)
    assert destino.read_bytes() == anterior
    assert list(destino.parent.iterdir()) == [destino]


def test_sidecar_com_evidencia_corrompida_e_descartado(tmp_path):
    perfil = resolver_texto("I (28M) answered.")
    destino = save_profile(perfil, tmp_path)
    data = json.loads(destino.read_text(encoding="utf-8"))
    data["evidence"][0]["weight"] = "invalido"
    destino.write_text(json.dumps(data), encoding="utf-8")
    assert load_profile("historia", tmp_path, perfil.source_sha256, "1") is None


def test_id_nao_pode_escapar_do_diretorio_de_perfis(tmp_path):
    perfil = resolver_sem_llm().resolve(story_id="../fora", title="Title", original_text="No clue.")
    with pytest.raises(ValueError):
        save_profile(perfil, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("genero,termo", [("male", "man"), ("female", "woman")])
def test_baixa_confianca_preserva_melhor_evidencia_sem_empatar(genero, termo):
    texto = f"I identify as a {termo}."
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, genero, .4, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="low", title="Title", original_text=texto)
    assert perfil.narration_gender == genero
    assert perfil.source_gender == "unknown"
    assert perfil.confidence == .4
    assert perfil.decision_method == "weighted"


def test_semantica_aceita_atribuicao_de_identidade_ao_narrador():
    texto = "They described me as a woman."
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, "female", .94, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="atribuicao", title="Title", original_text=texto)
    assert perfil.source_gender == "female"
    assert perfil.decision_method == "semantic"


@pytest.mark.parametrize("texto,esperado", [
    ("My sister said, ‘I am a woman.’", "unknown"),
    ("My sister said, ‘I am a woman.’ I (31M) disagreed.", "male"),
    ("My sister said, ‘I’m a woman.’ I (31M) disagreed.", "male"),
    ("People assume I am a woman because I have long hair.", "unknown"),
    ("I (28M) have long hair. People assume I am a woman.", "male"),
    ("My neighbors believe that I am a woman.", "unknown"),
    ("They thought I identify as a woman.", "unknown"),
])
@pytest.mark.parametrize("semantica", [False, True])
def test_citacao_curva_e_crenca_alheia_nao_identificam_narrador(texto, esperado, semantica):
    def provider(chunk):
        return [NarratorEvidence("semantic", texto, -1, "female", 1, "narrator", "groq")]
    resolver = NarratorProfileResolver({}, semantic_provider=provider, semantic_enabled=semantica)
    perfil = resolver.resolve(story_id="atribuicao-alheia", title="Title", original_text=texto)
    assert perfil.source_gender == esperado
    assert not any(e.gender == "female" for e in perfil.evidence)
    if esperado == "male":
        assert perfil.narration_gender == "male"
        assert perfil.decision_method == "explicit"
    else:
        assert perfil.evidence == ()
        assert perfil.decision_method == "stable_tiebreak"


def test_correcao_da_crenca_alheia_preserva_autoidentificacao_real():
    perfil = resolver_texto("People assume I am a woman, but I am a man.")
    assert perfil.source_gender == "male"
    assert perfil.narration_gender == "male"
    assert [e.quote for e in perfil.evidence] == ["I am a man"]


@pytest.mark.parametrize("marcador,genero", [("28M", "male"), ("28F", "female")])
def test_crenca_em_outra_oracao_nao_contamina_autoidentificacao(marcador, genero):
    perfil = resolver_texto(f"They think I look feminine, and I ({marcador}) disagree.")
    assert perfil.source_gender == genero
    assert perfil.narration_gender == genero
    assert perfil.decision_method == "explicit"
    assert [e.quote for e in perfil.evidence] == [f"I ({marcador})"]


def test_oracao_coordenada_com_sua_propria_crenca_continua_excluida():
    perfil = resolver_texto("They think I look feminine, and they assume I am a woman.")
    assert perfil.source_gender == "unknown"
    assert perfil.evidence == ()


@pytest.mark.parametrize("termo", ["woman", "man"])
@pytest.mark.parametrize("semantica", [False, True])
def test_coordenacao_sem_novo_sujeito_preserva_contexto_de_crenca(termo, semantica):
    texto = f"They assume I am a {termo}, and keep insisting I am a {termo}."
    genero = "female" if termo == "woman" else "male"
    resolver = NarratorProfileResolver({}, semantic_enabled=semantica, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", texto, -1, genero, 1, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="mesmo-sujeito", title="Title", original_text=texto)
    assert perfil.source_gender == "unknown"
    assert perfil.evidence == ()
    assert perfil.decision_method == "stable_tiebreak"


def test_crenca_continuada_nao_apaga_oracao_independente_do_narrador():
    perfil = resolver_texto(
        "They assume I am a woman, and keep insisting I am a woman, and I (28M) disagree."
    )
    assert perfil.source_gender == "male"
    assert perfil.narration_gender == "male"
    assert [e.quote for e in perfil.evidence] == ["I (28M)"]


@pytest.mark.parametrize("sujeito", ["my response", "the answer"])
@pytest.mark.parametrize("conjuncao", ["and", "or", "so"])
@pytest.mark.parametrize("marcador,genero,suposicao", [
    ("28M", "male", "woman"), ("28F", "female", "man"),
])
def test_sujeito_nominal_encerra_crenca_da_oracao_anterior(sujeito, conjuncao, marcador, genero, suposicao):
    perfil = resolver_texto(
        f"They assume I am a {suposicao}, {conjuncao} {sujeito} is that I ({marcador}) disagree."
    )
    assert perfil.source_gender == genero
    assert perfil.narration_gender == genero
    assert perfil.decision_method == "explicit"
    assert [e.quote for e in perfil.evidence] == [f"I ({marcador})"]


@pytest.mark.parametrize("genero,termo,suposicao", [
    ("male", "man", "woman"), ("female", "woman", "man"),
])
def test_sujeito_nominal_preserva_autoidentificacao_semantica(genero, termo, suposicao):
    texto = f"They assume I am a {suposicao}, and my response is that I identify as a {termo}."
    quote = f"I identify as a {termo}"
    resolver = NarratorProfileResolver({}, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", quote, -1, genero, 1, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="resposta-nominal", title="Title", original_text=texto)
    assert perfil.source_gender == genero
    assert perfil.narration_gender == genero
    assert perfil.decision_method == "semantic"
    assert [e.quote for e in perfil.evidence] == [quote]


@pytest.mark.parametrize("marcador,genero,suposicao", [
    ("28M", "male", "woman"), ("28F", "female", "man"),
])
@pytest.mark.parametrize("semantica", [False, True])
def test_sujeito_nominal_com_crenca_exclui_so_a_alegacao_governada(marcador, genero, suposicao, semantica):
    texto = (
        f"They assume I am a {suposicao}, and my family believes I am a {suposicao}, "
        f"and my response is that I ({marcador}) disagree."
    )
    genero_suposto = "female" if suposicao == "woman" else "male"
    resolver = NarratorProfileResolver({}, semantic_enabled=semantica, semantic_provider=lambda chunk: [
        NarratorEvidence("semantic", f"I am a {suposicao}", -1, genero_suposto, 1, "narrator", "groq"),
    ])
    perfil = resolver.resolve(story_id="crenca-nominal", title="Title", original_text=texto)
    assert perfil.source_gender == genero
    assert perfil.narration_gender == genero
    assert [e.quote for e in perfil.evidence] == [f"I ({marcador})"]
