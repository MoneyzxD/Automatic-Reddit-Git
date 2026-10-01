import json

import pytest

from stages.narrator_profile import NarratorProfile
from stages.script_guardian import TextPatch, parse_semantic_review, validate_and_apply_patches

from types import SimpleNamespace
from stages.language_tool import LanguageIssue, LanguageToolUnavailable
from stages.script_guardian import ScriptGuardian, QualityRejected, QualityUnavailable


@pytest.fixture
def perfil_feminino():
    return NarratorProfile(
        profile_id="pf", story_id="s1", source_gender="female",
        narration_gender="female", confidence=1.0, decision_method="explicit",
        evidence=(), resolver_version="1",
    )


def resposta(approved, issues):
    return json.dumps({"approved": approved, "issues": issues})


def achado(**overrides):
    item = {
        "original": "agora sou faxineiro", "replacement": "agora sou faxineira",
        "category": "narrator_gender", "severity": "critical", "subject": "narrator",
        "reason": "incompatível com o perfil", "source_quote": "I am a cleaner",
    }
    item.update(overrides)
    return item


@pytest.mark.parametrize("raw", [None, "", "not json", "{truncated"])
def test_resposta_ausente_ou_invalida_e_unavailable(raw):
    outcome = parse_semantic_review(raw)
    assert outcome.status == "unavailable"
    assert not outcome.approved


def test_approved_true_com_issue_critico_e_rejected():
    outcome = parse_semantic_review(resposta(True, [achado()]))
    assert outcome.status == "rejected"
    assert outcome.issues[0].severity == "critical"
    assert outcome.patches[0].replacement == "agora sou faxineira"


def test_string_false_nao_vira_booleano_true():
    assert parse_semantic_review(resposta("false", [])).status == "unavailable"


@pytest.mark.parametrize("item", [
    achado(severity="urgent"), achado(category="unknown"),
    achado(reason=4), achado(start=True), "não é objeto",
])
def test_issue_malformada_nao_e_aprovada(item):
    assert parse_semantic_review(resposta(True, [item])).status == "unavailable"


def test_aprovacao_sem_achados_e_reprovacao_sem_criticos():
    assert parse_semantic_review(resposta(True, [])).status == "approved"
    assert parse_semantic_review(resposta(False, [achado(severity="warning")])).status == "rejected"


def patch_para(original, replacement="corrigido", subject="narrator", **overrides):
    data = dict(
        original=original, replacement=replacement, category="narrator_gender",
        severity="critical", subject=subject, reason="teste", source_quote="source",
    )
    data.update(overrides)
    return TextPatch(**data)


def test_patch_muda_apenas_ocorrencia_unica(perfil_feminino):
    text = "Depois disso, agora sou faxineiro e sigo trabalhando."
    patch = patch_para(
        "agora sou faxineiro", "agora sou faxineira",
        source_quote="I now work as a cleaner",
    )
    result = validate_and_apply_patches(text, [patch], "I now work as a cleaner", perfil_feminino)
    assert result.text == "Depois disso, agora sou faxineira e sigo trabalhando."
    assert result.applied == (patch,)
    assert result.rejected == ()


@pytest.mark.parametrize("candidate,original", [
    ("trecho inexistente", "não existe"),
    ("repetido repetido", "repetido"),
    ("aaa!", "aa"),
])
def test_patch_ausente_ou_ambiguo_e_rejeitado(candidate, original, perfil_feminino):
    patch = patch_para(original)
    result = validate_and_apply_patches(candidate, [patch], "source", perfil_feminino)
    assert result.text == candidate
    assert result.rejected == (patch,)


def test_patch_de_genero_de_outro_personagem_e_rejeitado(perfil_feminino):
    patch = patch_para("meu irmão estava cansado", "meu irmão estava cansada", subject="brother")
    result = validate_and_apply_patches("Ontem, meu irmão estava cansado.", [patch], "source", perfil_feminino)
    assert result.rejected == (patch,)


@pytest.mark.parametrize("category", [
    "narrator_gender", "factual", "amount", "relationship", "identity",
    "outcome", "negation", "event", "continuity", "attribution", "omission", "terminology",
])
def test_mudanca_semantica_exige_citacao_literal(category, perfil_feminino):
    patch = patch_para("uma mudança", "outra mudança", category=category, source_quote="inventada")
    result = validate_and_apply_patches("Fiz uma mudança ontem.", [patch], "source", perfil_feminino)
    assert result.rejected == (patch,)


@pytest.mark.parametrize("category", ["grammar", "style", "language"])
def test_correcao_textual_exata_nao_exige_citacao(category, perfil_feminino):
    patch = patch_para("mal escrito", "bem escrito", category=category, source_quote="")
    result = validate_and_apply_patches("Estava mal escrito ontem.", [patch], "source", perfil_feminino)
    assert result.text == "Estava bem escrito ontem."


@pytest.mark.parametrize("original,replacement", [
    ("", "novo"), ("velho", ""), ("velho", "velho"),
])
def test_patch_vazio_ou_sem_alteracao_e_rejeitado(original, replacement, perfil_feminino):
    patch = patch_para(original, replacement)
    assert validate_and_apply_patches("velho texto", [patch], "source", perfil_feminino).rejected == (patch,)


def test_posicao_explica_ocorrencia_repetida(perfil_feminino):
    patch = patch_para("azul", "verde", start=5)
    result = validate_and_apply_patches("azul azul", [patch], "source", perfil_feminino)
    assert result.text == "azul verde"


def test_posicao_explica_ocorrencia_sobreposta(perfil_feminino):
    patch = patch_para("aa", "bb", start=1)
    result = validate_and_apply_patches("aaa!", [patch], "source", perfil_feminino)
    assert result.text == "abb!"
    assert result.applied == (patch,)


def test_posicao_invalida_e_rejeitada(perfil_feminino):
    patch = patch_para("azul", "verde", start=True)
    assert validate_and_apply_patches("azul azul", [patch], "source", perfil_feminino).rejected == (patch,)


def test_patches_sobrepostos_nao_reescrevem_mesmo_trecho(perfil_feminino):
    first = patch_para("gato", "gata", start=0)
    second = patch_para("ato", "ota", start=1)
    result = validate_and_apply_patches("gato preto", [first, second], "source", perfil_feminino)
    assert result.text == "gata preto"
    assert result.applied == (first,)
    assert result.rejected == (second,)


def test_patches_fora_de_ordem_preservam_trechos_nao_tocados(perfil_feminino):
    later = patch_para("preto", "branco", start=5)
    earlier = patch_para("gato", "gata", start=0)
    result = validate_and_apply_patches("gato preto!", [later, earlier], "source", perfil_feminino)
    assert result.text == "gata branco!"
    assert result.applied == (later, earlier)


def test_reescrita_integral_e_rejeitada(perfil_feminino):
    patch = patch_para("Meu roteiro inteiro.", "Outro roteiro inteiro.")
    result = validate_and_apply_patches("Meu roteiro inteiro.", [patch], "source", perfil_feminino)
    assert result.rejected == (patch,)


class FakeLanguageTool:
    def __init__(self, responses=()):
        self.responses = list(responses)
        self.calls = 0

    def check(self, text, language):
        self.calls += 1
        return self.responses.pop(0) if self.responses else ()

    def health(self, expected_version="6.6"):
        return SimpleNamespace(version=expected_version, locales=("pt-BR", "en-US", "es"))


class FakeSemanticReviewer:
    def __init__(self, responses=(), facts=None):
        self.responses = list(responses)
        self.facts = facts
        self.calls = []

    def review(self, **kwargs):
        self.calls.append(SimpleNamespace(**kwargs))
        if kwargs["mode"] == "facts":
            return self.facts if self.facts is not None else json.dumps({"facts": [{
                "kind": "event", "value": kwargs["source_chunk"],
                "source_quote": kwargs["source_chunk"],
            }]})
        return self.responses.pop(0) if self.responses else resposta(True, [])


def guardian_fake(tmp_path, semantic=None, lt=None, **config):
    return ScriptGuardian(
        {"fail_closed": True, "max_repair_attempts": 2, **config}, base_dir=tmp_path,
        languagetool=lt or FakeLanguageTool(),
        semantic_reviewer=semantic or FakeSemanticReviewer(),
    )


def revisar(guardian, perfil, **kwargs):
    return guardian.review_and_fix(**{
        "source_text": "I am a cleaner.", "candidate_text": "Agora sou faxineiro.",
        "language": "pt", "stage": "translation", "story_id": "s1", "profile": perfil,
        **kwargs,
    })


def test_guardiao_revisa_semantica_depois_do_patch(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([resposta(False, [achado(
        original="Agora sou faxineiro", replacement="Agora sou faxineira",
    )])])
    lt = FakeLanguageTool([(LanguageIssue("TEST", "GRAMMAR", "teste", ("faxineira",), 10, 19, "faxineiro"),)])
    guardian = guardian_fake(tmp_path, semantic, lt)
    review = revisar(guardian, perfil_feminino, final_gate=True)
    assert review.status == "approved"
    assert review.approved_text == "Agora sou faxineira."
    assert lt.calls == 2
    assert any(c.mode == "chunk" and "faxineira" in c.candidate_text for c in semantic.calls)
    assert any(c.mode == "global" and "faxineira" in c.candidate_text for c in semantic.calls)
    records = [json.loads(line) for line in review.report_path.read_text(encoding="utf-8").splitlines()]
    assert [r["status"] for r in records] == ["repairing", "approved"]
    assert records[0]["accepted_patches"]
    assert records[-1]["profile_id"] == "pf"


@pytest.mark.parametrize("candidate,original,replacement,source", [
    ("Ontem meu irmão estava cansado.", "meu irmão estava cansado", "meu irmão estava cansada", "My brother was tired."),
    ("Agora sou faxineira.", "Agora sou faxineira", "Agora sou faxineiro", "I am a cleaner."),
])
def test_recheck_bloqueia_patch_com_sujeito_ou_genero_falso(tmp_path, perfil_feminino, candidate, original, replacement, source):
    class Reviewer(FakeSemanticReviewer):
        def review(self, **kwargs):
            if kwargs["mode"] == "facts":
                return super().review(**kwargs)
            self.calls.append(SimpleNamespace(**kwargs))
            return resposta(False, [achado(
                original=original if original in kwargs["candidate_text"] else replacement,
                replacement=replacement, source_quote=source,
            )])
    semantic = Reviewer()
    with pytest.raises(QualityRejected) as error:
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino, candidate_text=candidate, source_text=source)
    assert any(replacement in c.candidate_text for c in semantic.calls if c.mode != "facts")
    assert error.value.review.status == "rejected"


def test_traducao_mista_curta_nunca_aprova(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([resposta(False, [achado(
        original="dog", replacement="", category="language", source_quote="", reason="idioma misturado",
    )])] * 2)
    with pytest.raises(QualityRejected):
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino, source_text="The dog.", candidate_text="O dog.")


@pytest.mark.parametrize("raw", [None, "prefixo " + resposta(True, []), resposta(True, [achado(source_quote="inventada")])])
def test_resposta_invalida_esgota_retries_sem_aprovar(tmp_path, perfil_feminino, raw):
    semantic = FakeSemanticReviewer([raw] * 10)
    with pytest.raises(QualityUnavailable):
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino, final_gate=True)
    assert len([c for c in semantic.calls if c.mode != "facts"]) == 3


def test_fatos_exigem_citacao_literal_e_schema_distinto(tmp_path, perfil_feminino):
    for facts in [resposta(True, []), '{"facts":[{"kind":"event","value":"x","source_quote":"inventado"}]}']:
        with pytest.raises(QualityUnavailable):
            revisar(guardian_fake(tmp_path, FakeSemanticReviewer(facts=facts)), perfil_feminino)


def test_cobertura_total_fatos_no_fim_e_cache(tmp_path, perfil_feminino):
    source = "Earlier context. " * 40 + "The surgery never existed."
    candidate = "Contexto anterior. " * 30 + "A cirurgia foi cancelada."
    semantic = FakeSemanticReviewer()
    guardian = guardian_fake(tmp_path, semantic, chunk_chars=100)
    first = revisar(guardian, perfil_feminino, source_text=source, candidate_text=candidate)
    facts_calls = [c for c in semantic.calls if c.mode == "facts"]
    assert "".join(c.source_chunk for c in facts_calls) == source
    assert "The surgery never existed." in first.factual_context
    chunks = [c for c in semantic.calls if c.mode == "chunk"]
    assert "".join(c.candidate_text for c in chunks) == candidate
    assert all("The surgery never existed." in c.factual_context for c in chunks)
    assert semantic.calls[-1].mode == "global"
    revisar(guardian, perfil_feminino, source_text=source, candidate_text=candidate)
    assert len([c for c in semantic.calls if c.mode == "facts"]) == len(facts_calls)


def test_omissao_global_bloqueia_mesmo_chunks_aprovados(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([resposta(True, []), resposta(False, [achado(
        original="", replacement="", category="omission", source_quote="I am a cleaner",
    )])])
    with pytest.raises(QualityRejected):
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino)


def test_estilo_so_avisa(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([resposta(False, [achado(
        original="", replacement="", category="style", severity="warning", source_quote="",
    )])])
    review = revisar(guardian_fake(tmp_path, semantic), perfil_feminino)
    assert review.status == "approved"
    assert review.issues[0].severity == "warning"


def test_dependencia_obrigatoria_falha_no_preflight(tmp_path):
    class Down(FakeLanguageTool):
        def health(self, **kwargs):
            raise LanguageToolUnavailable("secret=NAO_LOGAR")
    guardian = guardian_fake(tmp_path, lt=Down())
    with pytest.raises(QualityUnavailable):
        guardian.assert_ready()


def test_indisponibilidade_nao_bloqueante_continua_unavailable(tmp_path, perfil_feminino):
    guardian = guardian_fake(tmp_path, FakeSemanticReviewer([None] * 10), fail_closed=False)
    assert revisar(guardian, perfil_feminino).status == "unavailable"
    with pytest.raises(QualityUnavailable):
        revisar(guardian, perfil_feminino, final_gate=True)


def test_glossario_real_corrige_somente_conceito_configurado(tmp_path, perfil_feminino):
    guardian = guardian_fake(tmp_path)
    review = revisar(guardian, perfil_feminino,
        source_text="I bought a Pokémon card with my credit card.",
        candidate_text="Comprei cartão Pokémon com meu cartão de crédito.")
    assert review.approved_text == "Comprei carta Pokémon com meu cartão de crédito."
    assert review.changed


def test_indisponibilidade_apos_patch_nunca_aprova(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([
        resposta(False, [achado(original="Agora sou faxineiro", replacement="Agora sou faxineira")]),
        resposta(True, []), None, None, None,
    ])
    with pytest.raises(QualityUnavailable) as error:
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino)
    assert error.value.review.changed
    assert len([c for c in semantic.calls if c.mode == "chunk"]) == 4


def test_teto_de_reparos_ainda_exige_ultima_revisao(tmp_path, perfil_feminino):
    class Reviewer(FakeSemanticReviewer):
        def review(self, **kwargs):
            if kwargs["mode"] == "facts":
                return super().review(**kwargs)
            self.calls.append(SimpleNamespace(**kwargs))
            return resposta(False, [achado(
                original="velho" if "velho" in kwargs["candidate_text"] else "novo",
                replacement="novo" if "velho" in kwargs["candidate_text"] else "velho",
                category="grammar", source_quote="",
            )])
    semantic = Reviewer()
    guardian = guardian_fake(tmp_path, semantic)
    with pytest.raises(QualityRejected) as error:
        revisar(guardian, perfil_feminino, candidate_text="Um texto velho.")
    assert error.value.review.attempts == 3
    assert len(error.value.review.patches) == 2
    assert len([c for c in semantic.calls if c.mode == "global"]) == 3


def test_limite_de_contexto_nao_corta_texto(tmp_path, perfil_feminino):
    with pytest.raises(QualityUnavailable) as error:
        revisar(guardian_fake(tmp_path, max_context_chars=10), perfil_feminino)
    assert "limite" in error.value.review.issues[-1].message


def test_posicao_de_patch_nao_pode_sair_do_chunk_revisado(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer([resposta(False, [achado(
        original="velho", replacement="novo", category="grammar", source_quote="", start=6,
    )])])
    with pytest.raises(QualityRejected) as error:
        revisar(guardian_fake(tmp_path, semantic, chunk_chars=6), perfil_feminino,
                candidate_text="Teste velho.")
    assert error.value.review.approved_text == "Teste velho."
    assert not error.value.review.changed


def test_fatos_cacheados_nao_atravessam_idiomas_e_sao_deduplicados(tmp_path, perfil_feminino):
    fact = {"kind": "event", "value": "trabalha com limpeza", "source_quote": "cleaner"}
    semantic = FakeSemanticReviewer(facts=json.dumps({"facts": [fact, fact]}))
    guardian = guardian_fake(tmp_path, semantic)
    review = revisar(guardian, perfil_feminino)
    assert json.loads(review.factual_context) == [fact]
    revisar(guardian, perfil_feminino, language="es")
    assert [c.language for c in semantic.calls if c.mode == "facts"] == ["pt", "es"]


def test_telemetria_append_only_redige_chaves_aninhadas(tmp_path):
    from utils.telemetry import append_quality_report
    path = tmp_path / "quality.jsonl"
    append_quality_report(path, {"status": "approved"})
    before = path.read_bytes()
    append_quality_report(path, {"nested": [{"ACCESS_TOKEN": "NAO_GRAVAR", "client_secret": "NAO_GRAVAR",
                                           "Cookie": "NAO_GRAVAR", "authorization": "NAO_GRAVAR",
                                           "GROQ_API_KEY_PT": "NAO_GRAVAR", "ok": 1}]})
    assert path.read_bytes().startswith(before)
    assert "NAO_GRAVAR" not in path.read_text(encoding="utf-8")
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[1])["nested"][0]["ok"] == 1


def test_adapter_padrao_usa_chave_fixa_por_idioma_e_json_estrito(tmp_path, perfil_feminino, monkeypatch):
    import stages.script_guardian as module
    import utils.groq_client as groq_client
    keys, clients, calls = [], [], []

    def get_key(language):
        keys.append(language)
        return "chave-opaca"

    def create(**kwargs):
        calls.append(kwargs)
        context = json.loads(kwargs["messages"][1]["content"])
        raw = json.dumps({"facts": []}) if context["mode"] == "facts" else resposta(True, [])
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=raw))])

    def tracked(key, stage):
        clients.append((key, stage))
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    monkeypatch.setattr(module.env, "groq_api_key", get_key)
    monkeypatch.setattr(groq_client, "tracked_groq", tracked)
    guardian = ScriptGuardian({}, base_dir=tmp_path, languagetool=FakeLanguageTool())
    assert revisar(guardian, perfil_feminino).status == "approved"
    assert keys == ["pt"] * 3
    assert clients == [("chave-opaca", "script_guardian")] * 3
    assert all(c["temperature"] == 0 and c["response_format"] == {"type": "json_object"} for c in calls)
    assert "recortes deliberados" in calls[-1]["messages"][0]["content"]


def test_excecoes_do_provider_nao_vazam_no_relatorio(tmp_path, perfil_feminino):
    class Reviewer:
        def review(self, **kwargs):
            raise RuntimeError("authorization=SEGREDO_PESSOAL")
    guardian = guardian_fake(tmp_path, Reviewer())
    with pytest.raises(QualityUnavailable):
        revisar(guardian, perfil_feminino)
    assert "SEGREDO_PESSOAL" not in guardian.report_path.read_text(encoding="utf-8")


def test_fonte_curta_integral_chega_ao_global_mesmo_sem_fatos(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer(facts='{"facts":[]}')
    revisar(guardian_fake(tmp_path, semantic), perfil_feminino)
    assert semantic.calls[-1].source_chunk == "I am a cleaner."


def test_fonte_longa_sem_fatos_por_bloco_bloqueia(tmp_path, perfil_feminino):
    semantic = FakeSemanticReviewer(facts='{"facts":[]}')
    with pytest.raises(QualityUnavailable):
        revisar(guardian_fake(tmp_path, semantic, chunk_chars=10), perfil_feminino)
    assert len(semantic.calls) == 3
    assert all(c.mode == "facts" for c in semantic.calls)


@pytest.mark.parametrize("language,candidate", [("pt", "cartão Pokémon"), ("es", "tarjeta Pokémon")])
def test_glossario_findings_exige_fonte_contextual(tmp_path, language, candidate):
    guardian = guardian_fake(tmp_path)
    assert guardian.glossary.findings("I have a credit card.", candidate, language) == ()
    patch, = guardian.glossary.findings("I have a Pokémon card.", candidate, language)
    assert patch.original == candidate
    assert patch.source_quote == "Pokémon card"
    assert patch.replacement == "carta Pokémon"


@pytest.mark.parametrize("overrides", [{"language": "fr"}, {"candidate_text": " "}, {"story_id": "outro"}, {"profile": None}])
def test_entrada_invalida_nao_roda_dependencias(tmp_path, perfil_feminino, overrides):
    semantic = FakeSemanticReviewer()
    with pytest.raises(ValueError):
        revisar(guardian_fake(tmp_path, semantic), perfil_feminino, **overrides)
    assert semantic.calls == []
