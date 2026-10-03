"""O guardião controla seu retry; etapas legadas conservam o wrapper."""
from types import SimpleNamespace

import pytest

from utils import groq_client, telemetry


def cliente_fake(monkeypatch, failures):
    constructor, calls = [], []
    def create(**kwargs):
        calls.append(kwargs)
        if failures:
            raise failures.pop(0)
        return SimpleNamespace(choices=[], usage=SimpleNamespace(prompt_tokens=2, completion_tokens=3, total_tokens=5))
    def groq(**kwargs):
        constructor.append(kwargs)
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    import groq as sdk
    monkeypatch.setattr(sdk, "Groq", groq)
    telemetry.reset()
    return constructor, calls


def rate_limit():
    exc = RuntimeError("SEGREDO_TESTE")
    exc.status_code = 429
    return exc


def test_guardiao_nao_multiplica_retry_do_sdk_e_wrapper(monkeypatch):
    constructor, calls = cliente_fake(monkeypatch, [rate_limit()])
    client = groq_client.tracked_groq("opaque", "script_guardian", sdk_max_retries=0,
                                     retry_rate_limit=False, timeout=60)
    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="model", messages=[])
    assert constructor == [{"api_key": "opaque", "max_retries": 0, "timeout": 60}]
    assert len(calls) == 1


def test_chamador_legado_preserva_retry_e_telemetria(monkeypatch):
    constructor, calls = cliente_fake(monkeypatch, [rate_limit()])
    waits = []
    monkeypatch.setattr(groq_client.time, "sleep", waits.append)
    groq_client.tracked_groq("opaque", "adapter").chat.completions.create(model="model", messages=[])
    assert constructor == [{"api_key": "opaque"}]
    assert len(calls) == 2
    assert waits == [15]
    assert telemetry.usage_by_stage()["adapter"]["total"] == 5
