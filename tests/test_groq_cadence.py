"""Cadência real do wrapper com transporte HTTP isolado, sem chamar a Groq."""
import json

import httpx
import pytest
from groq import Groq

from utils import groq_client, telemetry


@pytest.fixture
def clock(monkeypatch):
    now = [100.0]
    waits = []

    def sleep(seconds):
        waits.append(seconds)
        now[0] += seconds

    monkeypatch.setattr(groq_client, "_NEXT_REQUEST_AT", {}, raising=False)
    monkeypatch.setattr(groq_client.time, "monotonic", lambda: now[0])
    monkeypatch.setattr(groq_client.time, "sleep", sleep)
    telemetry.reset()
    return now, waits


def transport(monkeypatch, clock, headers, *, error_first=False):
    calls = []

    def handle(request):
        calls.append((clock[0][0], json.loads(request.content)))
        if error_first and len(calls) == 1:
            return httpx.Response(400, json={"error": {"code": "json_validate_failed",
                                  "message": "synthetic private body"}})
        return httpx.Response(200, headers=headers, json={
            "id": "synthetic", "object": "chat.completion", "created": 1, "model": "model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 2000, "completion_tokens": 100, "total_tokens": 2100},
        })

    import groq
    monkeypatch.setattr(groq, "Groq", lambda **kwargs: Groq(**kwargs,
                        http_client=httpx.Client(transport=httpx.MockTransport(handle))))
    return calls


def complete(key="synthetic-key", stage="script_guardian", model="model"):
    return groq_client.tracked_groq(key, stage, sdk_max_retries=0,
                                  retry_rate_limit=False).chat.completions.create(
        model=model, messages=[{"role": "user", "content": "synthetic"}])


def test_etapas_e_clientes_recriados_aguardam_recarga_tpm(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {"x-ratelimit-reset-tokens": "24.5s",
                      "x-ratelimit-reset-requests": "23h"})
    assert complete(stage="adapter").choices[0].message.content == "OK"
    assert complete(stage="script_guardian").choices[0].message.content == "OK"
    assert calls[1][0] - calls[0][0] >= 24.5
    assert sum(clock[1]) < 60
    assert telemetry.usage_by_stage()["script_guardian"]["total"] == 2100


@pytest.mark.parametrize("mode", ["facts", "chunk", "global"])
@pytest.mark.parametrize("model", [None, "qwen/qwen3.8-27b"])
def test_sdk_serializa_contrato_estrito_do_guardiao_no_corpo_http(clock, monkeypatch, mode, model):
    from stages.script_guardian import _GroqReviewer
    from utils import environment

    calls = transport(monkeypatch, clock, {})
    monkeypatch.setattr(environment, "groq_api_key", lambda language: "synthetic-key")
    config = {"semantic_timeout_seconds": 60}
    if model:
        config["groq_model"] = model
    _GroqReviewer(config).review(
        mode=mode, language="pt", candidate_text="Texto sintético.", source_chunk="Fonte sintética.")
    request = calls[0][1]
    assert request["model"] == (model or "openai/gpt-oss-20b")
    assert request["reasoning_effort"] == ("none" if model == "qwen/qwen3.8-27b" else "low")
    assert request["max_completion_tokens"] == 2048
    assert request["response_format"]["type"] == "json_schema"
    contract = request["response_format"]["json_schema"]
    assert contract["strict"] is True
    schema = contract["schema"]
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(schema["properties"])
    collection = "facts" if mode == "facts" else "issues"
    item = schema["properties"][collection]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == set(item["properties"])
    if mode != "facts":
        assert item["properties"]["start"] == {"type": ["integer", "null"]}
    assert not request.get("stream") and not request.get("tools")


def test_chaves_distintas_nao_assumem_organizacoes_distintas(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {"x-ratelimit-reset-tokens": "12s"})
    complete(key="fixed-pt")
    complete(key="fixed-en")
    assert calls[1][0] - calls[0][0] >= 12


@pytest.mark.parametrize("reset", [None, "NaN", "Infinity", "-1s", "23h", "garbage"])
def test_header_ausente_ou_invalido_usa_janela_conservadora(clock, monkeypatch, reset):
    calls = transport(monkeypatch, clock, {} if reset is None else {"x-ratelimit-reset-tokens": reset})
    complete()
    complete()
    assert calls[1][0] - calls[0][0] >= 60
    assert all(0 < wait <= 60 for wait in clock[1])


def test_tentativa_rejeitada_tambem_reserva_janela(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {}, error_first=True)
    with pytest.raises(Exception) as failure:
        complete()
    assert failure.value.status_code == 400
    complete()
    assert calls[1][0] - calls[0][0] >= 60


def test_modelos_distintos_nao_compartilham_recarga(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {"x-ratelimit-reset-tokens": "30s"})
    complete(model="model-a")
    complete(model="model-b")
    assert calls[1][0] == calls[0][0]


def test_recarga_zero_nao_cria_rajada_acima_de_30_rpm(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {"x-ratelimit-reset-tokens": "0s"})
    for _ in range(32):
        complete()
    assert calls[30][0] - calls[0][0] >= 60


def test_recarga_de_90s_respeita_header_sem_sleep_longo(clock, monkeypatch):
    calls = transport(monkeypatch, clock, {"x-ratelimit-reset-tokens": "1m30s"})
    complete()
    complete()
    assert 90 <= calls[1][0] - calls[0][0] <= 120
    assert all(0 < wait <= 60 for wait in clock[1])
