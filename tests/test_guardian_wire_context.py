"""O contexto no HTTP pode ser compacto, nunca perder evidência literal."""
import json

import pytest

from stages.script_guardian import _GroqReviewer


def _wire(monkeypatch, factual_context, source_chunk):
    import utils.groq_client

    captured = {}

    class API:
        def create(self, **kwargs):
            captured.update(kwargs)
            from types import SimpleNamespace
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(
                    content='{"approved":true,"issues":[]}'))])

    from types import SimpleNamespace
    monkeypatch.setattr(utils.groq_client, "tracked_groq", lambda *a, **k:
                        SimpleNamespace(chat=SimpleNamespace(completions=API())))
    monkeypatch.setenv("GROQ_API_KEY_EN", "chave-sintetica-sem-rede")
    _GroqReviewer({"semantic_timeout_seconds": 5}).review(
        mode="chunk", source_chunk=source_chunk, candidate_text="Texto candidato",
        factual_context=factual_context, language="en", stage="adaptation",
        profile={"narration_gender": "male"},
    )
    return json.loads(captured["messages"][1]["content"]), captured


def _decode(wire):
    # Decodificador independente: contrato mínimo lido pelo consumidor.
    restored = []
    for fact in wire["factual_context"]:
        fact = dict(fact)
        if "source_quote_ref" in fact:
            ref = fact.pop("source_quote_ref")
            assert set(ref) == {"field", "start", "end"}
            assert ref["field"] == "source_chunk"
            fact["source_quote"] = wire[ref["field"]][ref["start"]:ref["end"]]
        restored.append(fact)
    return restored


def test_wire_remove_repeticao_mas_preserva_todos_os_fatos(monkeypatch):
    source = "Meu filho pediu quinze mil reais para uma cirurgia que nunca aconteceu. " * 25
    facts = [{"kind": "amount", "value": "quinze mil reais", "source_quote": source},
             {"kind": "event", "value": "cirurgia inexistente", "source_quote": source}]
    old = json.dumps(facts, ensure_ascii=False)
    wire, captured = _wire(monkeypatch, old, source)
    assert isinstance(wire["factual_context"], list)
    assert _decode(wire) == facts
    assert len(captured["messages"][1]["content"]) < len(old) + len(source)
    assert wire["candidate_text"] == "Texto candidato"
    assert wire["profile"] == {"narration_gender": "male"}
    assert wire["stage"] == "adaptation"
    assert captured["max_completion_tokens"] == 2048


@pytest.mark.parametrize("source, quote", [
    ("Ação: fui faxineiro e não faxineira.", "fui faxineiro"),
    ("A palavra carta aparece duas vezes: carta.", "carta"),
    ("Antes.\nDepois não paguei.", "\nDepois não paguei."),
    ("Trecho parcial da fonte", "Citação fora do chunk mas existente na fonte completa"),
    ("Trecho", ""),
])
def test_literalidade_continua_integra_com_unicode_repeticao_e_citacao_externa(monkeypatch, source, quote):
    facts = [{"kind": "event", "value": "valor original", "source_quote": quote}]
    wire, _ = _wire(monkeypatch, json.dumps(facts, ensure_ascii=False), source)
    assert _decode(wire) == facts
    if quote and quote in source:
        assert "source_quote_ref" in wire["factual_context"][0]
        assert "source_quote" not in wire["factual_context"][0]
    else:
        assert wire["factual_context"][0]["source_quote"] == quote


@pytest.mark.parametrize("value", [
    "não é JSON", '{"facts":[]}', '[{"kind":"event"}]',
    '[{"kind":"event","value":"v","source_quote":"x","extra":"preservar"}]',
])
def test_contexto_nao_tipificado_nunca_tem_campos_descartados(monkeypatch, value):
    wire, _ = _wire(monkeypatch, value, "x")
    assert wire["factual_context"] == value
