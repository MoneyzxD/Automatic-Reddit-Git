import json
from types import SimpleNamespace

import pytest

from stages.language_tool import LanguageIssue
from stages.narrator_profile import NarratorProfile
from stages.script_guardian import QualityRejected, QualityUnavailable, ScriptGuardian


SOURCE = "I bought two plants, and my sister watered them. I kept ten seeds."
CANDIDATE = SOURCE.replace("plants, and", "plants and")


def grammar_patch(original="plants and", replacement="plants, and"):
    return dict(original=original, replacement=replacement, category="grammar",
                severity="critical", subject="narrator", reason="Corrigir a forma.",
                source_quote="", start=None)


def exercise(tmp_path, *, empty=False, attack=False, upstream_failure=False, primary=False, **config):
    calls, checked = [], []

    class LT:
        def health(self, **kwargs):
            return SimpleNamespace(version="6.6", locales=("pt-BR", "en-US", "es"))

        def check(self, text, language):
            checked.append(text)
            start = text.find("plants and")
            return () if start < 0 else (LanguageIssue(
                "COMMA_COMPOUND_SENTENCE", "PUNCTUATION", "Missing comma before and.",
                ("plants, and",), start, start + len("plants and"), "plants and"),)

    class Reviewer:
        def review(self, **context):
            calls.append(context)
            mode = context["mode"]
            if mode == "facts":
                return json.dumps({"facts": []})
            if upstream_failure and mode != "language":
                raise TimeoutError()
            issues = []
            if (mode == "language" or primary and mode == "chunk" and "plants and" in context["candidate_text"]) and not empty:
                issues = [grammar_patch()]
                if attack:
                    issues.append(grammar_patch("ten seeds", "one hundred seeds"))
            elif "one hundred seeds" in context["candidate_text"]:
                issues = [dict(grammar_patch("one hundred seeds", ""), category="amount",
                               source_quote=SOURCE, reason="Quantidade diferente da fonte.")]
            return json.dumps({"approved": not issues, "issues": issues})

    guardian = ScriptGuardian({"semantic_retry_wait_seconds": 0, **config},
        base_dir=tmp_path, languagetool=LT(), semantic_reviewer=Reviewer())
    profile = NarratorProfile("profile", "incident", "male", "male", 1.0, "explicit", (), "1")
    args = dict(source_text=SOURCE, candidate_text=CANDIDATE, language="en",
                stage="adaptation", story_id="incident", profile=profile)
    return guardian, args, calls, checked


def test_reparo_dirigido_apos_revisao_vazia_exige_rechecagem_completa(tmp_path):
    guardian, args, calls, checked = exercise(tmp_path)
    result = guardian.review_and_fix(**args)
    assert result.approved_text == SOURCE and result.status == "approved"
    assert [c["mode"] for c in calls] == ["facts", "chunk", "global", "language", "chunk", "global"]
    assert checked == [CANDIDATE, SOURCE]
    focused = next(c for c in calls if c["mode"] == "language")
    assert focused["language_tool_findings"][0]["rule_id"] == "COMMA_COMPOUND_SENTENCE"
    assert "source_chunk" not in focused and "factual_context" not in focused
    assert all(c["candidate_text"] == SOURCE for c in calls[-2:])


def test_reparo_gramatical_nao_aprova_mudanca_factual(tmp_path):
    guardian, args, calls, checked = exercise(tmp_path, attack=True)
    with pytest.raises(QualityRejected) as caught:
        guardian.review_and_fix(**args)
    assert any(i.category == "amount" for i in caught.value.review.issues)
    assert checked[-1].endswith("one hundred seeds.")
    assert calls[-1]["mode"] == "global"


@pytest.mark.parametrize("config,expected", [({}, 1), ({"max_repair_attempts": 0}, 0)])
def test_sem_reparo_seguro_ou_orcamento_continua_bloqueado(tmp_path, config, expected):
    guardian, args, calls, checked = exercise(tmp_path, empty=True, **config)
    with pytest.raises(QualityRejected) as caught:
        guardian.review_and_fix(**args)
    assert caught.value.review.approved_text == CANDIDATE
    assert len([c for c in calls if c["mode"] == "language"]) == expected
    assert checked == [CANDIDATE]


def test_indisponibilidade_semantica_nao_dispara_reparo_alternativo(tmp_path):
    guardian, args, calls, _ = exercise(tmp_path, upstream_failure=True)
    with pytest.raises(QualityUnavailable):
        guardian.review_and_fix(**args)
    assert not any(c["mode"] == "language" for c in calls)


@pytest.mark.parametrize("primary", [True, False])
def test_sem_necessidade_de_reparo_dirigido_nao_consume_chamada_extra(tmp_path, primary):
    guardian, args, calls, _ = exercise(tmp_path, primary=primary)
    if not primary:
        args["candidate_text"] = SOURCE
    assert guardian.review_and_fix(**args).status == "approved"
    assert not any(c["mode"] == "language" for c in calls)


@pytest.mark.parametrize("mode", ["chunk", "global", "language"])
def test_achados_repetidos_chegam_ancorados_aos_blocos_nativos(monkeypatch, mode):
    from utils import environment, llm_client
    from stages.script_guardian import _GroqReviewer

    text = "".join(f"At station {i}, I planted roses and my sister watered lilies and the volunteer swept paths. "
                   for i in range(7))
    starts = [i for i in range(len(text)) if text.startswith(" and", i)]
    findings = [dict(finding_id=f"lt{i}", rule_id="COMMA_COMPOUND_SENTENCE",
                     original=" and", start=start, end=start + 4,
                     message="Missing comma.", replacements=[", and"])
                for i, start in enumerate(starts)]
    requests = []

    def create(**kwargs):
        requests.append(kwargs)
        data = {"approved": True, "issues": []}
        if mode != "language":
            data["language_issues"] = []
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
            message=SimpleNamespace(content=json.dumps(data)))])

    monkeypatch.setattr(environment, "llm_api_key", lambda *args: "opaque")
    monkeypatch.setattr(llm_client, "tracked_llm", lambda *args, **kwargs:
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    context = dict(mode=mode, language="en", candidate_text=text, language_tool_findings=findings)
    if mode != "language":
        context.update(source_chunk=text, factual_context="[]")
    _GroqReviewer({"semantic_timeout_seconds": 60}).review(**context)
    wire = json.loads(requests[0]["messages"][1]["content"])
    units = {u["id"]: u["text"] for u in wire["candidate_units"]}
    assert "candidate_text" not in wire
    assert len(wire["language_tool_findings"]) == len(findings)
    for finding in wire["language_tool_findings"]:
        start, end = finding["start"], finding["end"]
        literal = finding["context_before"] + finding["original"] + finding["context_after"]
        assert literal == text[max(0, start - 40):min(len(text), end + 40)]
        assert literal in "".join(units[uid] for uid in finding["candidate_unit_ids"])
    if mode == "language":
        schema = requests[0]["response_format"]["json_schema"]["schema"]
        fields = schema["properties"]["issues"]["items"]["properties"]
        assert fields["category"]["enum"] == ["grammar", "language"]
        assert fields["source_quote"]["enum"] == [""]
        assert "candidate_unit_ids" in fields and "start" not in fields


@pytest.mark.parametrize("original,expected", [("blue box and", "blue box, and"), (" and", None)])
def test_reparo_nativo_resolve_ancora_literal_mas_rejeita_ocorrencia_ambigua(
    monkeypatch, original, expected,
):
    from utils import environment, llm_client
    from stages.script_guardian import _CandidateReferenceError, _GroqReviewer, parse_semantic_review

    text = "🌱 I filled a blue box and she filled a red box and we planted seeds."
    item = grammar_patch(original, expected or ", and")
    item.pop("start")
    item["candidate_unit_ids"] = ["c0"]
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
            message=SimpleNamespace(content=json.dumps({"approved": False, "issues": [item]})))])

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setattr(environment, "llm_api_key", lambda *args: "opaque")
    monkeypatch.setattr(llm_client, "tracked_llm", lambda *args, **kwargs: client)
    reviewer = _GroqReviewer({"semantic_timeout_seconds": 60})
    if expected is None:
        with pytest.raises(_CandidateReferenceError) as caught:
            reviewer.review(mode="language", language="en", candidate_text=text)
        assert caught.value.code == "ambiguous_original"
    else:
        result = parse_semantic_review(reviewer.review(mode="language", language="en", candidate_text=text))
        assert result.patches[0].start == text.index(original)
        assert result.patches[0].replacement == expected
