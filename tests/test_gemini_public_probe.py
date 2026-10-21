import json

import pytest

from scripts import probe_gemini_public as probe
from utils import gemini_client


@pytest.mark.parametrize("status,expected", [(200, 0), (503, 2)])
def test_sonda_sintetica_faz_uma_chamada_sem_repetir_diagnostico_privado(monkeypatch, capsys, status, expected):
    from types import SimpleNamespace
    monkeypatch.setenv("GEMINI_API_KEY", "segredo-sintetico")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "gemini")
    monkeypatch.setattr(gemini_client, "_NEXT_REQUEST_AT", {})
    calls = []
    def post(url, **options):
        calls.append(options)
        wire = options["json"]["contents"][0]["parts"][0]["text"]
        assert "synthetic-public" in wire and "1x6sq3x" not in wire
        assert "x-goog-api-key" in options["headers"] and options["timeout"] == 60
        body = {"candidates": [{"finishReason": "STOP", "content": {"parts": [
            {"text": '{"approved":true,"issues":[],"language_issues":[]}'}]}}]}
        return SimpleNamespace(status_code=status, headers={}, json=lambda: body, close=lambda: None)
    monkeypatch.setattr(gemini_client.requests, "post", post)
    assert probe.main() == expected and len(calls) == 1
    output = capsys.readouterr().out
    assert json.loads(output)["generation_calls"] == 1
    assert "segredo-sintetico" not in output and "Preparei" not in output
