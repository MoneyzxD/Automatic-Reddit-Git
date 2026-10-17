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
            data = {"approved": True, "issues": []}
            properties = kwargs["response_format"]["json_schema"]["schema"]["properties"]
            if "language_issues" in properties:
                data["language_issues"] = []
            return SimpleNamespace(choices=[SimpleNamespace(
                finish_reason="stop", message=SimpleNamespace(
                    content=json.dumps(data)))])

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
            assert isinstance(ref, list) and len(ref) == 2
            start, end = ref
            assert type(start) is int and type(end) is int
            fact["source_quote"] = wire["source_chunk"][start:end]
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
    assert "".join(unit["text"] for unit in wire["candidate_units"]) == "Texto candidato"
    assert wire["profile"] == {"narration_gender": "male"}
    assert wire["stage"] == "adaptation"
    assert captured["max_completion_tokens"] == 2048


def test_instrucao_geral_cabe_sem_remover_contratos_criticos(monkeypatch):
    _, captured = _wire(monkeypatch, json.dumps([
        {"kind": "event", "value": "fato", "source_quote": "Fonte literal"}
    ]), "Fonte literal")
    instruction = captured["messages"][0]["content"]
    # O incidente tinha espaço no contexto, mas estourou TPM com instrução/schema.
    assert len(instruction) <= 5000
    for contract in ("perfil é imutável", "grávido", "minha própria comida", "me", "mim",
                     "en-US", "recortes deliberados", "source_quote_ref", "candidate_unit_ids",
                     "language_issues", "invalid_source_reference", "nonliteral_evidence"):
        assert contract in instruction


def test_referencias_compactas_reduzem_estrutura_preservando_ledger_inteiro(monkeypatch):
    source = "Ação literal: nunca paguei a cirurgia.\n"
    facts = [{"kind": "event", "value": f"Fato {i}", "source_quote": source}
             for i in range(44)]
    wire, captured = _wire(monkeypatch, json.dumps(facts, ensure_ascii=False), source)
    old = [{"kind": f["kind"], "value": f["value"], "source_quote_ref":
            {"field": "source_chunk", "start": 0, "end": len(source)}} for f in facts]
    encoded = lambda value: json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    assert _decode(wire) == facts
    assert len(encoded(old)) - len(encoded(wire["factual_context"])) >= 1500
    assert "source_quote_ref=[start,end]" in captured["messages"][0]["content"]


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


@pytest.mark.parametrize("redundant", [True, False])
def test_limite_nativo_conta_wire_real_sem_descartar_citacoes(monkeypatch, tmp_path, redundant):
    from types import SimpleNamespace
    from utils import environment, llm_client
    from stages.script_guardian import ScriptGuardian, _ReviewUnavailable

    captured = []
    source = "The narrator gave a library card to a cousin. " * 25 if redundant else "Hi."
    facts = [{"kind": "event", "value": f"Event {i}", "source_quote": source}
             for i in range(30)] if redundant else []
    raw = json.dumps(facts, ensure_ascii=False)
    assert not redundant or len(raw) > 24000

    def create(**kwargs):
        captured.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
            content=json.dumps({"approved": True, "issues": [], "language_issues": []})))])

    monkeypatch.setattr(environment, "llm_api_key", lambda *args: "opaque")
    monkeypatch.setattr(llm_client, "tracked_llm", lambda *args, **kwargs:
        SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    limit = 24000 if redundant else 80
    guardian = ScriptGuardian({"max_context_chars": limit}, base_dir=tmp_path)
    args = dict(mode="global", source_text=source, source_chunk=source, language="en",
                candidate_text="A library card.", factual_context=raw)
    if redundant:
        assert guardian._request(**args).approved
        body = captured[0]["messages"][1]["content"]
        assert len(body) <= limit
        assert _decode(json.loads(body)) == facts
    else:
        # IDs e metadados também custam espaço; não basta contar só os valores.
        with pytest.raises(_ReviewUnavailable) as caught:
            guardian._request(**args)
        assert caught.value.failure.code == "context_limit"
        assert not captured
