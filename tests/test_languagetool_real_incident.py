"""Regressão no LanguageTool real do runner, sem chamadas de LLM."""
import os

import pytest

from stages.language_tool import LanguageToolClient


pytestmark = pytest.mark.skipif(not os.getenv("LANGUAGETOOL_URL"),
                                reason="Runtime local de LanguageTool não configurado")


def test_marcador_pt_do_splitter_nao_introduz_erro_de_acento():
    from stages.splitter import CONTINUITY_MARKERS
    client = LanguageToolClient({})
    # O marcador do incidente confundia a análise morfológica de Continua.
    assert any(f.rule_id == "DIACRITICS" for f in client.check("[Continua na Parte 2 de 2...]", "pt"))
    marker = CONTINUITY_MARKERS["pt"]["end"].format(next=2, total=2)
    assert not client.check(marker, "pt")


def test_backend_real_nao_trata_fleetingly_como_substantivo_antes_de_mentioned():
    client = LanguageToolClient({})
    text = "It was a normal message that I fleetingly mentioned to a roommate."
    with client._post(text, "en-US") as response:
        response.raise_for_status()
        matches = response.json()["matches"]
    assert any(m["rule"]["id"] == "PRP_VB" for m in matches)
    assert not any(i.rule_id == "PRP_VB" for i in client.check(text, "en"))
    assert any(i.rule_id == "YOUR_YOU_2" for i in client.check("You device isn't working.", "en"))
    assert any(i.rule_id == "PRP_VB" for i in client.check("I fleetingly device.", "en"))


@pytest.mark.parametrize("quote", ["I told you you’re not going.", "I told you you're not going."])
def test_backend_real_confirma_repeticao_aparente_com_contracao(quote):
    client = LanguageToolClient({})
    with client._post(quote, "en-US") as response:
        response.raise_for_status()
        matches = response.json()["matches"]
    assert any(m["rule"]["id"] == "ENGLISH_WORD_REPEAT_RULE" for m in matches)
    assert not any(i.rule_id == "ENGLISH_WORD_REPEAT_RULE" for i in client.check(quote, "en"))
    assert any(i.rule_id == "ENGLISH_WORD_REPEAT_RULE" for i in client.check("I miss you you.", "en"))


def test_guardiao_real_preserva_pronomes_sem_perder_repeticao_incorreta(tmp_path):
    import json
    from types import SimpleNamespace
    from stages.script_guardian import ScriptGuardian, QualityRejected
    from stages.narrator_profile import NarratorProfile
    def semantic(**context):
        return json.dumps({"facts": []} if context["mode"] == "facts" else {"approved": True, "issues": []})
    guardian = ScriptGuardian({}, base_dir=tmp_path, semantic_reviewer=SimpleNamespace(review=semantic))
    profile = NarratorProfile("pf", "s1", "male", "male", 1.0, "explicit", (), "1")
    for text, expected in (("I told you you’re not going.", "approved"), ("I miss you you.", "rejected"),
                           ("I told you you’re not going. I miss you you.", "rejected")):
        if expected == "rejected":
            with pytest.raises(QualityRejected) as caught:
                guardian.review_and_fix(source_text=text, candidate_text=text, language="en",
                    stage="adaptation", story_id="s1", profile=profile)
            review = caught.value.review
        else:
            review = guardian.review_and_fix(source_text=text, candidate_text=text, language="en",
                stage="adaptation", story_id="s1", profile=profile)
        assert review.status == expected and review.approved_text == text


def test_regra_real_nao_introduz_crase_em_todas_as_vezes():
    client = LanguageToolClient({})
    client.health()
    text = "Falhei todas as vezes."
    with client._post(text, "pt-BR") as response:
        response.raise_for_status()
        raw = response.json()
    assert any(match["rule"]["id"] == "AS_VEZES_BR" for match in raw["matches"])
    assert not any(issue.rule_id == "AS_VEZES_BR" for issue in client.check(text, "pt"))


def test_regra_real_continua_detectando_crase_ausente():
    client = LanguageToolClient({})
    findings = client.check("Eu as vezes fico triste.", "pt")
    assert any(issue.rule_id == "AS_VEZES_BR" and "às vezes" in issue.replacements
               for issue in findings)


def test_backend_real_confirma_lacuna_parentalidade_sem_aceitar_erro_proximo():
    client = LanguageToolClient({})
    with client._post("A parentalidade importa.", "pt-BR") as response:
        response.raise_for_status()
        matches = response.json()["matches"]
    assert any(m["rule"]["id"] == "MORFOLOGIK_RULE_PT_BR" for m in matches)
    assert not any(i.rule_id == "MORFOLOGIK_RULE_PT_BR" for i in client.check("A parentalidade importa.", "pt"))
    assert any(i.rule_id == "MORFOLOGIK_RULE_PT_BR" for i in client.check("A parentaliade importa.", "pt"))


def test_backend_real_identifica_depois_de_como_estilo_formal():
    client = LanguageToolClient({})
    findings = client.check("Isto tudo depois de saber os resultados.", "pt")
    formal = [i for i in findings if i.rule_id == "DEPOIS_DE_APÓS"]
    assert formal and all(i.issue_type == "style" and i.category == "FORMAL" for i in formal)


def test_guardiao_com_backend_real_preserva_vocabulo_e_estilo_sem_ciclo(tmp_path):
    import json
    from types import SimpleNamespace
    from stages.script_guardian import ScriptGuardian
    from stages.narrator_profile import NarratorProfile
    def semantic(**context):
        if context["mode"] == "facts":
            return json.dumps({"facts": []})
        return json.dumps({"approved": True, "issues": []})
    guardian = ScriptGuardian({}, base_dir=tmp_path, semantic_reviewer=SimpleNamespace(review=semantic))
    profile = NarratorProfile("pf", "s1", "female", "female", 1.0, "explicit", (), "1")
    text = "Pensei na parentalidade depois de saber os resultados."
    review = guardian.review_and_fix(source_text="I thought about parenting after learning the results.",
        candidate_text=text, language="pt", stage="translation", story_id="s1", profile=profile)
    assert review.status == "approved" and review.approved_text == text
    assert review.attempts == 1 and not review.patches
