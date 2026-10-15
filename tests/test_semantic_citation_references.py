"""Citações do revisor são resolvidas localmente, nunca reescritas pelo modelo."""
import json
from types import SimpleNamespace

import pytest

from stages.script_guardian import (_GroqReviewer, ScriptGuardian, QualityUnavailable,
    _source_quote_registry, _semantic_response_format, _generation_schema_diagnostic,
    _restore_review_citations, REVIEW_CATEGORIES)
from stages.narrator_profile import NarratorProfile


SOURCE = "I didn't lend money.\r\nThen I paid 50 dollars. 🧾"
FACTS = [{"kind": "event", "value": "No loan", "source_quote": "I didn't lend money."},
         {"kind": "amount", "value": "Payment of 50 dollars", "source_quote": "Then I paid 50 dollars. 🧾"}]


def wire_review(issues):
    optional = {"grammar", "style", "language"}
    return {"approved": not issues,
            "issues": [i for i in issues if i["category"] not in optional],
            "language_issues": [i for i in issues if i["category"] in optional]}


def review(monkeypatch, issues, **config):
    import utils.groq_client
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            content=json.dumps({"approved": not issues, "issues": issues} if config.get("semantic_citation_ids") is False
                               else wire_review(issues))))])
    monkeypatch.setenv("GROQ_API_KEY_PT", "chave-falsa-sem-rede")
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    context = dict(mode="chunk", language="pt", stage="translation", source_chunk=SOURCE,
                   candidate_text="Não emprestei dinheiro. Depois paguei 50 reais.",
                   factual_context=json.dumps(FACTS), profile={"narration_gender": "female"})
    before = json.dumps(context, sort_keys=True)
    result = _GroqReviewer({"semantic_timeout_seconds": 30, "groq_model": "qwen/qwen3.8-27b", **config}).review(**context)
    assert json.dumps(context, sort_keys=True) == before
    return json.loads(result), captured


def issue(**overrides):
    return {"original": "50 reais", "replacement": "50 dólares", "category": "amount",
            "severity": "critical", "subject": "narrator", "reason": "Preservar moeda",
            "source_quote_id": "f1", "start": None, **overrides}


def test_referencia_copia_citacao_literal_e_mantem_schema_fechado(monkeypatch):
    result, captured = review(monkeypatch, [issue()])
    assert result["issues"][0]["source_quote"] == FACTS[1]["source_quote"]
    assert "source_quote_id" not in result["issues"][0]
    properties = captured["response_format"]["json_schema"]["schema"]["properties"]
    for collection in ("issues", "language_issues"):
        fields = properties[collection]["items"]
        assert "source_quote" not in fields["properties"] and fields["additionalProperties"] is False
        assert set(fields["required"]) == set(fields["properties"])
        if "amount" in fields["properties"]["category"]["enum"]:
            assert fields["properties"]["source_quote_id"] == {"type": "string", "enum": ["f0", "f1", "s0"]}
    assert captured["max_completion_tokens"] == 2048 and captured["reasoning_effort"] == "none"
    instruction = captured["messages"][0]["content"]
    assert "nunca source_quote_ref, IDs" not in instruction
    assert "Copie source_quote exatamente" not in instruction
    example, _ = json.JSONDecoder().raw_decode(instruction[instruction.index('{"approved"'):])
    assert _generation_schema_diagnostic(json.dumps(example), captured["response_format"])[0] == "matches_schema"


def test_gramatica_sem_citacao_continua_sem_evidencia_inventada(monkeypatch):
    result, _ = review(monkeypatch, [issue(category="grammar", source_quote_id="")])
    assert result["issues"][0]["source_quote"] == ""


def test_as_duas_listas_preservam_todos_os_achados_criticos(monkeypatch):
    from stages.script_guardian import parse_semantic_review
    result, _ = review(monkeypatch, [issue(), issue(category="grammar", source_quote_id="")])
    assert set(result) == {"approved", "issues"} and len(result["issues"]) == 2
    assert result["issues"][0]["source_quote"] == FACTS[1]["source_quote"]
    assert result["issues"][1]["source_quote"] == ""
    assert parse_semantic_review(json.dumps(result)).status == "rejected"


@pytest.mark.parametrize("facts", [[], FACTS[:1]])
def test_fonte_preserva_evidencia_omitida_do_ledger(facts):
    registry = _source_quote_registry({"factual_context": json.dumps(facts), "source_chunk": SOURCE})
    assert registry["s0"] == SOURCE


def test_contexto_invalido_preserva_contrato_anterior_e_global_sem_fonte():
    assert _source_quote_registry({"factual_context": "inválido", "source_chunk": SOURCE}) is None
    assert _source_quote_registry({"factual_context": json.dumps(FACTS), "source_chunk": ""}) == {
        "f0": FACTS[0]["source_quote"], "f1": FACTS[1]["source_quote"]}
    assert _source_quote_registry({"factual_context": "[]", "source_chunk": ""}) is None


@pytest.mark.parametrize("category", REVIEW_CATEGORIES)
@pytest.mark.parametrize("reference", ["", "s0"])
def test_schema_exige_referencia_para_as_mesmas_categorias_do_gate(category, reference):
    contract = _semantic_response_format("qwen/qwen3.8-27b", "chunk", quote_ids=("f0", "s0"))
    raw = json.dumps(wire_review([issue(category=category, source_quote_id=reference)]))
    status, errors, truncated = _generation_schema_diagnostic(raw, contract)
    allowed = bool(reference) or category in {"grammar", "style", "language"}
    assert status == ("matches_schema" if allowed else "mismatch")
    assert bool(errors) == (not allowed) and not truncated


@pytest.mark.parametrize("category,collection", [("amount", "issues"), ("grammar", "language_issues")])
def test_diagnostico_listas_preserva_campos_ausentes_sem_valores_privados(category, collection):
    contract = _semantic_response_format("qwen/qwen3.8-27b", "chunk", quote_ids=("s0",))
    item = issue(category=category, source_quote_id="s0")
    del item["reason"]
    item["PRIVATE_EXTRA"] = "PRIVATE_VALUE"
    _, errors, _ = _generation_schema_diagnostic(json.dumps(wire_review([item])), contract)
    assert {"path": f"$.{collection}[0].reason", "rule": "required"} in errors
    assert "PRIVATE" not in json.dumps(errors)


@pytest.mark.parametrize("changes", [
    {"source_quote_id": "PRIVATE_UNKNOWN"}, {"source_quote_id": []},
    {"source_quote_id": None}, {"source_quote": "PRIVATE_PARAPHRASE"},
])
def test_referencia_invalida_ou_citacao_livre_nao_e_consumida(monkeypatch, changes):
    with pytest.raises(ValueError) as caught:
        review(monkeypatch, [issue(**changes)])
    assert "PRIVATE" not in str(caught.value)


@pytest.mark.parametrize("category", [[], {}, None])
def test_categoria_de_tipo_invalido_tem_erro_controlado(category):
    raw = json.dumps({"approved": False, "issues": [issue(category=category)], "language_issues": []})
    with pytest.raises(ValueError) as caught:
        _restore_review_citations(raw, {"f1": SOURCE})
    assert caught.value.code == "invalid_fields"


@pytest.mark.parametrize("collection,category", [("issues", "grammar"), ("language_issues", "amount")])
def test_categoria_na_lista_errada_nao_e_reclassificada(collection, category):
    data = {"approved": False, "issues": [], "language_issues": []}
    data[collection].append(issue(category=category))
    with pytest.raises(ValueError):
        _restore_review_citations(json.dumps(data), {"f1": SOURCE})


def test_rejeicao_real_do_schema_tem_codigo_sanitizado():
    from dataclasses import asdict
    from stages.script_guardian import _provider_failure
    error = RuntimeError("PRIVATE_MESSAGE")
    error.status_code = 400
    error.body = {"error": {"schema_code": "discriminator_multiple_candidates",
                            "message": "PRIVATE_MESSAGE", "schema_path": "PRIVATE_PATH"}}
    failure = _provider_failure(error, "chunk", 1, 16218)
    assert failure.code == "provider_error" and failure.provider_code == "discriminator_multiple_candidates"
    assert "PRIVATE" not in json.dumps(asdict(failure))


def test_reversao_preserva_contrato_literal_anterior(monkeypatch):
    legacy = issue()
    del legacy["source_quote_id"]
    legacy["source_quote"] = FACTS[1]["source_quote"]
    result, captured = review(monkeypatch, [legacy], semantic_citation_ids=False)
    assert result["issues"] == [legacy]
    fields = captured["response_format"]["json_schema"]["schema"]["properties"]["issues"]["items"]["properties"]
    assert "source_quote" in fields and "source_quote_id" not in fields


@pytest.mark.parametrize("invalid_id,partial_ledger", [(False, False), (True, False), (False, True)])
def test_gate_completo_resolve_evidencia_ou_rejeita_id_sem_fallback(tmp_path, monkeypatch, invalid_id, partial_ledger):
    import utils.groq_client
    monkeypatch.setenv("GROQ_API_KEY_PT", "chave-falsa-sem-rede")
    calls = []
    def create(**kwargs):
        context = json.loads(kwargs["messages"][1]["content"])
        calls.append(context)
        if context["mode"] == "facts":
            data = {"facts": []} if partial_ledger else {"facts": [{"kind": "amount", "value": "Payment of 50 dollars",
                               "source_unit_ids": ["u0"]}]}
        else:
            issues = ([issue(source_quote_id="PRIVATE_UNKNOWN" if invalid_id else ("s0" if partial_ledger else "f0"))]
                      if "50 reais" in context["candidate_text"] else [])
            data = wire_review(issues)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            content=json.dumps(data)))])
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    lt = SimpleNamespace(health=lambda **kwargs: SimpleNamespace(version="6.6", locales=("pt-BR", "en-US", "es")),
                         check=lambda *args: ())
    guardian = ScriptGuardian({"groq_model": "qwen/qwen3.8-27b", "semantic_retry_wait_seconds": 0},
                               base_dir=tmp_path, languagetool=lt)
    profile = NarratorProfile("pf", "s1", "female", "female", 1.0, "explicit", (), "1")
    arguments = dict(source_text=SOURCE, candidate_text="Depois paguei 50 reais.", language="pt",
                     stage="translation", story_id="s1", profile=profile)
    if invalid_id:
        with pytest.raises(QualityUnavailable) as caught:
            guardian.review_and_fix(**arguments)
        assert caught.value.review.semantic_failure.code == "invalid_source_reference"
        assert caught.value.review.semantic_failure.source_reference_error == "unknown_id"
        assert caught.value.review.semantic_failure.attempts == 3
        assert "PRIVATE" not in guardian.report_path.read_text(encoding="utf-8")
        assert [call["mode"] for call in calls] == ["facts", "chunk", "chunk", "chunk"]
    else:
        result = guardian.review_and_fix(**arguments)
        assert result.status == "approved" and result.approved_text == "Depois paguei 50 dólares."
        assert result.patches[0].source_quote == SOURCE
        assert [call["mode"] for call in calls] == ["facts", "chunk", "global", "chunk", "global"]
