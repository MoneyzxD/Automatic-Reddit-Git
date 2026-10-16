"""Âncoras do candidato preservam ocorrência e texto; não inferem substituição global."""
import json
from types import SimpleNamespace

import pytest

from stages.script_guardian import (_candidate_unit_registry, _restore_review_citations,
    _semantic_response_format, _GroqReviewer, parse_semantic_review, validate_and_apply_patches,
    _anchor_semantic_patch)
from stages.narrator_profile import NarratorProfile


TEXT = "Minha amiga fala de mim mesma. " + "Texto de contexto. " * 28 + "Eu cuido de mim mesma. 🧾\r\n"


def item(ids):
    return {"original": "mim mesma", "replacement": "mim mesmo", "category": "narrator_gender",
            "severity": "critical", "subject": "narrator", "reason": "Concordar com o perfil masculino",
            "source_quote_id": "f0", "candidate_unit_ids": ids}


def restore(ids, *, text=TEXT, changes=None):
    value = item(ids)
    value.update(changes or {})
    return json.loads(_restore_review_citations(json.dumps({"approved": False, "issues": [value],
        "language_issues": []}), {"f0": "A male narrator cares for himself."},
        candidate_units=_candidate_unit_registry({"candidate_text": text})))


def test_ref_aplica_so_a_ocorrencia_selecionada_preservando_unicode():
    units = _candidate_unit_registry({"candidate_text": TEXT})
    assert "".join(unit.text for unit in units.values()) == TEXT
    selected = next(uid for uid, unit in reversed(list(units.items())) if "mim mesma" in unit.text)
    result = restore([selected])
    patch = parse_semantic_review(json.dumps(result)).patches[0]
    assert patch.start == TEXT.rindex("mim mesma")
    profile = NarratorProfile("pf", "s1", "male", "male", 1.0, "explicit", (), "1")
    fixed = validate_and_apply_patches(TEXT, [patch], "A male narrator cares for himself.", profile)
    assert len(fixed.applied) == 1
    assert fixed.text.startswith("Minha amiga fala de mim mesma.")
    assert fixed.text.endswith("Eu cuido de mim mesmo. 🧾\r\n")
    prefix = "Trecho anterior preservado. "
    anchored = _anchor_semantic_patch(TEXT, patch, len(prefix))
    assert anchored.start == len(prefix) + TEXT.rindex("mim mesma")
    joined = validate_and_apply_patches(prefix + TEXT, [anchored], "A male narrator cares for himself.", profile)
    assert joined.text == prefix + fixed.text


@pytest.mark.parametrize("ids,changes,code", [
    (["PRIVATE_UNKNOWN"], {}, "unknown_id"), (["c0", "c0"], {}, "duplicate_id"),
    (["c2", "c0"], {}, "noncontiguous"), (["c0", "c2"], {}, "noncontiguous"),
    ([False], {}, "invalid_type"), ([], {}, "empty"),
    (["c0"], {"original": "PRIVATE_NOT_PRESENT"}, "original_missing"),
])
def test_ref_invalida_bloqueia_sem_conteudo_privado(ids, changes, code):
    with pytest.raises(ValueError) as caught:
        restore(ids, changes=changes)
    assert "PRIVATE" not in str(caught.value)
    assert caught.value.code == code


def test_trecho_que_atravessa_unidades_contiguas_mantem_offset():
    result = restore(["c0", "c1"], text="x" * 196 + "mim mesma final")
    assert result["issues"][0]["start"] == 196


def test_duas_ocorrencias_na_mesma_unidade_continuam_ambiguas():
    with pytest.raises(ValueError) as caught:
        restore(["c0"], text="mim mesma, mim mesma")
    assert caught.value.code == "ambiguous_original"


def test_omissao_sem_patch_nao_inventa_ancora():
    result = restore([], changes={"original": "", "replacement": ""})
    assert result["issues"][0]["start"] is None
    assert parse_semantic_review(json.dumps(result)).status == "rejected"


def test_transporte_integro_sem_offsets_contados_pelo_modelo(monkeypatch):
    import utils.groq_client
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        wire = json.loads(kwargs["messages"][1]["content"])
        uid = next(unit["id"] for unit in reversed(wire["candidate_units"]) if "mim mesma" in unit["text"])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            content=json.dumps({"approved": False, "issues": [item([uid])], "language_issues": []})))])
    monkeypatch.setenv("GROQ_API_KEY_PT", "chave-falsa-sem-rede")
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    context = {"language": "pt", "mode": "chunk", "source_chunk": "A male narrator cares for himself.",
               "candidate_text": TEXT, "factual_context": json.dumps([
                   {"kind": "identity", "value": "male narrator", "source_quote": "A male narrator cares for himself."}])}
    before = json.dumps(context)
    result = json.loads(_GroqReviewer({"semantic_timeout_seconds": 30,
        "groq_model": "qwen/qwen3.8-27b"}).review(**context))
    assert json.dumps(context) == before and result["issues"][0]["start"] == TEXT.rindex("mim mesma")
    wire = json.loads(captured["messages"][1]["content"])
    assert "candidate_text" not in wire
    assert "".join(unit["text"] for unit in wire["candidate_units"]) == TEXT
    assert captured["max_completion_tokens"] == 2048 and captured["reasoning_effort"] == "none"
    fields = captured["response_format"]["json_schema"]["schema"]["properties"]["issues"]["items"]["properties"]
    assert "start" not in fields and fields["candidate_unit_ids"]["items"]["enum"] == list(_candidate_unit_registry(context))


def test_guardiao_mantem_tres_tentativas_e_nao_aplica_ref_desconhecida(tmp_path, monkeypatch):
    from stages.script_guardian import ScriptGuardian, QualityUnavailable
    import utils.groq_client
    calls = []
    def create(**kwargs):
        context = json.loads(kwargs["messages"][1]["content"])
        calls.append(context)
        data = ({"facts": []} if context["mode"] == "facts" else
                {"approved": False, "issues": [dict(item(["PRIVATE_UNKNOWN"]), source_quote_id="s0")],
                 "language_issues": []})
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(data)))])
    monkeypatch.setenv("GROQ_API_KEY_PT", "chave-falsa-sem-rede")
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    lt = SimpleNamespace(health=lambda **kw: SimpleNamespace(version="6.6", locales=("pt-BR", "en-US", "es")),
                         check=lambda *a: ())
    guardian = ScriptGuardian({"semantic_retry_wait_seconds": 0}, base_dir=tmp_path, languagetool=lt)
    profile = NarratorProfile("pf", "s1", "male", "male", 1.0, "explicit", (), "1")
    with pytest.raises(QualityUnavailable) as caught:
        guardian.review_and_fix(source_text="A male narrator cares for himself.", candidate_text=TEXT,
                                language="pt", stage="translation", story_id="s1", profile=profile)
    failure = caught.value.review.semantic_failure
    assert failure.code == "invalid_candidate_reference" and failure.attempts == 3
    assert caught.value.review.approved_text == TEXT and not caught.value.review.patches
    assert [call["mode"] for call in calls] == ["facts", "chunk", "chunk", "chunk"]
    assert "PRIVATE" not in guardian.report_path.read_text(encoding="utf-8")


def test_feedback_de_campo_de_ancora_ausente_e_controlado(tmp_path, monkeypatch):
    from stages.script_guardian import ScriptGuardian
    import utils.groq_client
    calls = []
    def create(**kwargs):
        context = json.loads(kwargs["messages"][1]["content"])
        calls.append(context)
        value = dict(item(["c0"]), source_quote_id="s0")
        if len(calls) == 1:
            del value["candidate_unit_ids"]
            error = RuntimeError("PRIVATE_MESSAGE")
            error.status_code = 400
            error.body = {"error": {"code": "json_validate_failed", "failed_generation": json.dumps(
                {"approved": False, "issues": [value], "language_issues": []})}}
            raise error
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=json.dumps(
            {"approved": False, "issues": [value], "language_issues": []})))])
    monkeypatch.setenv("GROQ_API_KEY_PT", "chave-falsa-sem-rede")
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    guardian = ScriptGuardian({"semantic_retry_wait_seconds": 0}, base_dir=tmp_path)
    result = guardian._request(mode="chunk", source_text="source", source_chunk="source", language="pt",
                               candidate_text="Eu cuido de mim mesma.", factual_context="[]")
    assert result.status == "rejected" and len(calls) == 2
    assert calls[1]["retry_feedback"]["missing_issue_fields"] == ["candidate_unit_ids"]
    assert "PRIVATE" not in json.dumps(calls)
