# conftest.py
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest


@pytest.fixture(autouse=True)
def provedor_legado_explicito(monkeypatch):
    """Regressões legadas usam mocks Groq; testes Gemini sobrescrevem a seleção."""
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
