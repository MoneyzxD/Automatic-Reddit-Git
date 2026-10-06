"""Diagnóstico numérico do HTTP real, sem rede, chaves ou roteiro nos registros."""
from dataclasses import asdict
import json
import logging

import httpx
import pytest
from groq import Groq

from stages.script_guardian import _provider_failure
from utils import groq_client, telemetry


@pytest.fixture(autouse=True)
def isolated_clock(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(groq_client, "_NEXT_REQUEST_AT", {})
    monkeypatch.setattr(groq_client.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(groq_client.time, "sleep", lambda seconds: now.__setitem__(0, now[0] + seconds))
    telemetry.reset()


def client(monkeypatch, *, status=200, headers=None):
    requests = []

    def handle(request):
        requests.append(request)
        if status != 200:
            return httpx.Response(status, headers=headers, json={"error": {
                "code": "rate_limit_exceeded", "message": "ROTEIRO_PRIVADO Authorization=CHAVE_PRIVADA"}})
        return httpx.Response(200, headers=headers, json={
            "id": "private-response-id", "object": "chat.completion", "created": 1,
            "model": "qwen/qwen3.8-27b", "choices": [{"index": 0, "message": {
                "role": "assistant", "content": "RESPOSTA_PRIVADA"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2000, "completion_tokens": 100, "total_tokens": 2100}})

    import groq
    monkeypatch.setattr(groq, "Groq", lambda **kwargs: Groq(**kwargs,
                        http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    wrapped = groq_client.tracked_groq("CHAVE_PRIVADA", "script_guardian", sdk_max_retries=0,
                                       retry_rate_limit=False)
    return wrapped, requests


def complete(wrapped, **kwargs):
    return wrapped.chat.completions.create(model="qwen/qwen3.8-27b",
        messages=[{"role": "system", "content": "Instrução ç"},
                  {"role": "user", "content": "ROTEIRO_PRIVADO"}],
        response_format={"type": "json_object"}, **kwargs)


def test_429_preserva_tamanho_http_limites_e_teto_efetivo_sem_conteudo(monkeypatch, tmp_path, caplog):
    wrapped, requests = client(monkeypatch, status=429, headers={
        "x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "420",
        "x-ratelimit-reset-tokens": "1m30.5s", "x-ratelimit-limit-requests": "1000",
        "x-ratelimit-remaining-requests": "999", "x-ratelimit-reset-requests": "2h3m4s",
        "retry-after": "90.5", "authorization": "CHAVE_PRIVADA", "x-request-id": "ID_PRIVADO"})
    caplog.set_level(logging.INFO)
    with pytest.raises(Exception) as caught:
        complete(wrapped, max_completion_tokens=10, extra_body={"max_completion_tokens": 321})
    # Retirar a captura do wrapper deve quebrar esta prova de diagnóstico persistido.
    failure = asdict(_provider_failure(caught.value, "chunk", 1, 16695))
    assert failure.get("transport_diagnostic") is not None
    diag = failure["transport_diagnostic"]
    assert diag["payload_bytes"] == len(requests[0].content)
    assert diag["payload_chars"] == len(requests[0].content.decode("utf-8"))
    assert diag["completion_cap"] == 321  # O SDK funde extra_body antes de enviar.
    assert diag["legacy_cap"] is None
    assert diag["limit_tpm"] == 8000 and diag["remaining_tpm"] == 420
    assert diag["limit_rpd"] == 1000 and diag["remaining_rpd"] == 999
    assert diag["reset_tpm_seconds"] == 90.5 and diag["reset_rpd_seconds"] == 7384
    assert diag["retry_after_seconds"] == 90.5
    assert diag["prompt"] is None and diag["http_status"] == 429
    assert len(requests) == 1  # O diagnóstico não acrescenta retries ou chamadas.
    report = tmp_path / "quality.jsonl"
    telemetry.append_quality_report(report, {"semantic_failure": failure})
    persisted = report.read_text(encoding="utf-8")
    assert json.loads(persisted)["semantic_failure"]["transport_diagnostic"] == diag
    for private in ("ROTEIRO_PRIVADO", "CHAVE_PRIVADA", "ID_PRIVADO", "private-response-id"):
        assert private not in persisted + caplog.text


def test_sucesso_emite_consumo_e_teto_ausente_sem_mudar_resposta(monkeypatch, caplog):
    wrapped, requests = client(monkeypatch, headers={"x-ratelimit-limit-tokens": "8000"})
    caplog.set_level(logging.INFO)
    response = complete(wrapped)
    assert response.choices[0].message.content == "RESPOSTA_PRIVADA"
    records = [r for r in caplog.records if r.message.startswith("Diagnóstico HTTP Groq: ")]
    assert len(records) == 1
    diag = json.loads(records[0].message.split(": ", 1)[1])
    assert (diag["prompt"], diag["completion"], diag["total"]) == (2000, 100, 2100)
    assert diag["completion_cap"] is None and diag["legacy_cap"] is None
    assert diag["limit_tpm"] == 8000 and diag["remaining_tpm"] is None
    assert diag["payload_bytes"] == len(requests[0].content)
    assert telemetry.usage_by_stage()["script_guardian"]["total"] == 2100
    assert "RESPOSTA_PRIVADA" not in caplog.text and "ROTEIRO_PRIVADO" not in caplog.text
    assert "max_completion_tokens" not in json.loads(requests[0].content)


@pytest.mark.parametrize("invalid", ["-1", "NaN", "Infinity", "CHAVE_PRIVADA", "1e200", "1.5"])
def test_cabecalhos_invalidos_nao_entram_no_diagnostico(monkeypatch, invalid):
    wrapped, _ = client(monkeypatch, status=429, headers={
        "x-ratelimit-limit-tokens": invalid, "x-ratelimit-remaining-requests": invalid,
        "x-ratelimit-reset-tokens": invalid, "retry-after": invalid})
    with pytest.raises(Exception) as caught:
        complete(wrapped)
    failure = asdict(_provider_failure(caught.value, "chunk", 1, 20))
    assert failure.get("transport_diagnostic") is not None
    diag = failure["transport_diagnostic"]
    assert diag["limit_tpm"] is None and diag["remaining_rpd"] is None
    assert diag["reset_tpm_seconds"] is None
    if invalid != "1.5":
        assert diag["retry_after_seconds"] is None


def test_fronteira_do_guardiao_descarta_campos_livres_e_valores_adulterados(tmp_path):
    exc = RuntimeError("CHAVE_PRIVADA")
    exc.status_code = 429
    exc.groq_diagnostic = {"limit_tpm": "CHAVE_PRIVADA", "remaining_tpm": True,
        "payload_bytes": -1, "prompt": 2000, "completion": float("inf"),
        "total": 10**100, "retry_after_seconds": float("nan"), "unknown": "ROTEIRO_PRIVADO"}
    failure = asdict(_provider_failure(exc, "chunk", 1, 20))
    assert failure.get("transport_diagnostic") is not None
    diag = failure["transport_diagnostic"]
    assert diag["prompt"] == 2000
    assert diag["limit_tpm"] is None and diag["remaining_tpm"] is None
    assert diag["payload_bytes"] is None and diag["completion"] is None and diag["total"] is None
    assert diag["retry_after_seconds"] is None and "unknown" not in diag
    assert "CHAVE_PRIVADA" not in json.dumps(failure)


def test_segundos_adulterados_nao_derrubam_diagnostico_do_guardiao():
    exc = RuntimeError("CHAVE_PRIVADA")
    exc.status_code = 429
    exc.groq_diagnostic = {"reset_tpm_seconds": 10**1000}
    failure = asdict(_provider_failure(exc, "chunk", 1, 20))
    assert failure["transport_diagnostic"]["reset_tpm_seconds"] is None


@pytest.mark.parametrize("status", [200, 429])
def test_falha_de_escrita_do_diagnostico_nao_altera_resultado(monkeypatch, status):
    wrapped, requests = client(monkeypatch, status=status)
    monkeypatch.setattr(groq_client.logger, "info", lambda *args, **kwargs: (_ for _ in ()).throw(OSError()))
    if status == 200:
        assert complete(wrapped).choices[0].message.content == "RESPOSTA_PRIVADA"
    else:
        with pytest.raises(Exception) as caught:
            complete(wrapped)
        assert caught.value.status_code == 429
        assert _provider_failure(caught.value, "chunk", 1, 20).transport_diagnostic["http_status"] == 429
    assert len(requests) == 1


@pytest.mark.parametrize("cap", [None, 123, True, "CHAVE_PRIVADA"])
def test_teto_no_corpo_http_e_validado_sem_inventar_default(monkeypatch, cap):
    wrapped, requests = client(monkeypatch, status=429)
    with pytest.raises(Exception) as caught:
        complete(wrapped, extra_body={"max_tokens": cap})
    diag = _provider_failure(caught.value, "chunk", 1, 20).transport_diagnostic
    assert diag["legacy_cap"] == (123 if type(cap) is int else None)
    assert diag["completion_cap"] is None
    assert json.loads(requests[0].content)["max_tokens"] == cap


def test_stream_nao_e_consumido_para_medir_diagnostico(monkeypatch, caplog):
    consumed = []

    class Body(httpx.SyncByteStream):
        def __iter__(self):
            consumed.append(True)
            yield b'data: {"private": "RESPOSTA_PRIVADA"}\n\n'

    import groq
    monkeypatch.setattr(groq, "Groq", lambda **kwargs: Groq(**kwargs,
        http_client=httpx.Client(transport=httpx.MockTransport(lambda request:
            httpx.Response(200, stream=Body(), headers={"content-type": "text/event-stream"})))))
    wrapped = groq_client.tracked_groq("CHAVE_PRIVADA", "script_guardian", sdk_max_retries=0,
                                      retry_rate_limit=False)
    caplog.set_level(logging.INFO)
    stream = complete(wrapped, stream=True)
    assert consumed == []
    records = [r for r in caplog.records if r.message.startswith("Diagnóstico HTTP Groq: ")]
    diag = json.loads(records[0].message.split(": ", 1)[1])
    assert diag["payload_bytes"] is None and diag["prompt"] is None
    assert "RESPOSTA_PRIVADA" not in caplog.text
    stream.close()
