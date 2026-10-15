import json
from types import SimpleNamespace

import pytest

from scripts.probe_groq_public import safe_error


@pytest.mark.parametrize("as_text", [True, False])
def test_diagnostico_identifica_cota_sem_copiar_mensagem(as_text):
    body = {"error": {"code": "rate_limit_exceeded", "message":
            "PRIVATE_CANARY organization PRIVATE_ORG TPD Limit 200000 Used 199000 Requested 3000"}}
    error = SimpleNamespace(status_code=429, body=json.dumps(body) if as_text else body)
    result = safe_error(error)
    assert result["http_status"] == 429 and result["limit_types"] == ["TPD"]
    assert result["limit"] == 200000 and result["used"] == 199000 and result["requested"] == 3000
    assert "PRIVATE" not in json.dumps(result)


def test_diagnostico_recusa_codigo_ou_corpo_livre():
    error = SimpleNamespace(status_code=503, body={"error": {"code": {"PRIVATE": "CANARY"},
                                                           "message": "PRIVATE_CANARY capacity"}})
    result = safe_error(error)
    assert result["provider_code"] == "other" and result["mentions_capacity"]
    assert "PRIVATE" not in json.dumps(result)
