import json

import pytest

from stages.narrator_profile import NarratorProfile
from stages.script_guardian import TextPatch, parse_semantic_review, validate_and_apply_patches


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
