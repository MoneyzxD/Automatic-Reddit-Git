"""Sonda avulsa não envia payload divergente nem faz retry de geração."""
import hashlib
import json
from types import SimpleNamespace

import pytest

from scripts import probe_gemini_review as probe


@pytest.mark.parametrize("valid_digest", [True, False])
def test_sonda_verifica_contexto_antes_da_unica_chamada(monkeypatch, capsys, valid_digest):
    raw = json.dumps({"mode": "chunk", "stage": "split_part", "language": "pt",
                      "profile": {"story_id": "1x6sq3x"}}).encode()
    env = {"PROBE_NAMESPACE": "validation-probe", "PROBE_ASSET_ID": "1",
           "PROBE_SHA256": hashlib.sha256(raw).hexdigest() if valid_digest else "0" * 64,
           "GEMINI_API_KEY": "SYNTHETIC", "PIPELINE_STATE_TOKEN": "SYNTHETIC",
           "PIPELINE_LLM_PROVIDER": "gemini"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(probe, "PrivateStateStore", lambda *args: SimpleNamespace(
        validate_target=lambda: None, _download=lambda asset, path, limit: path.write_bytes(raw)))
    calls = []
    def reviewer(config):
        assert config["semantic_timeout_seconds"] == 180
        def review(**context):
            calls.append(context)
            raise TimeoutError("SYNTHETIC_TOKEN_AND_STORY")
        return SimpleNamespace(context_chars=lambda **context: 8411, review=review)
    monkeypatch.setattr(probe, "_GroqReviewer", reviewer)
    assert probe.main() == 2
    output = capsys.readouterr().out
    assert "SYNTHETIC" not in output
    assert len(calls) == int(valid_digest)
    assert json.loads(output)["generation_calls"] == int(valid_digest)
