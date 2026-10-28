"""Uma credencial fixa por execução; o idioma do texto não muda a carga."""
import os
from types import SimpleNamespace

import pytest

from utils import environment
from scripts import generate_daily_batch


@pytest.mark.parametrize("workload", ["pt", "en", "es"])
def test_etapas_em_qualquer_idioma_usam_carga_fixa(monkeypatch, workload):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.setenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", workload)
    for lang in ("pt", "en", "es"):
        monkeypatch.setenv("GROQ_API_KEY_" + lang.upper(), "opaque-" + lang)
    for text_language in ("en", "pt", "es", ""):
        assert environment.llm_api_key(text_language) == "opaque-" + workload


def test_carga_sem_chave_nao_recorre_a_outro_idioma(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.setenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", "pt")
    monkeypatch.delenv("GROQ_API_KEY_PT", raising=False)
    monkeypatch.setenv("GROQ_API_KEY_EN", "opaque-en")
    monkeypatch.setenv("GROQ_API_KEY", "opaque-generic")
    assert environment.llm_api_key("en") == "opaque-generic"


def test_gemini_ignora_carga_groq(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "gemini")
    monkeypatch.setenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", "pt")
    monkeypatch.setenv("GEMINI_API_KEY", "opaque-gemini")
    assert environment.llm_api_key("en") == "opaque-gemini"


def test_sem_carga_preserva_escolha_legada_por_idioma(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.delenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", raising=False)
    monkeypatch.setenv("GROQ_API_KEY_PT", "opaque-pt")
    monkeypatch.setenv("GROQ_API_KEY_EN", "opaque-en")
    assert environment.llm_api_key("en") == "opaque-en"
    assert environment.llm_api_key("pt") == "opaque-pt"


def test_carga_invalida_nao_escolhe_credencial(monkeypatch):
    monkeypatch.setenv("PIPELINE_LLM_PROVIDER", "groq")
    monkeypatch.setenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", "other")
    with pytest.raises(ValueError):
        environment.llm_api_key("en")


@pytest.mark.parametrize("languages,expected", [(["pt"], "pt"), (["pt-br"], "pt"),
                                                  (["en"], "en"), (["pt", "en"], None)])
def test_filho_fixa_carga_sem_mudar_pai(monkeypatch, languages, expected):
    monkeypatch.setenv("PIPELINE_GROQ_WORKLOAD_LANGUAGE", "es")
    calls = []
    def launch(command, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(generate_daily_batch.subprocess, "run", launch)
    assert generate_daily_batch._executar_historia(languages, 3) == 0
    assert calls[0]["env"].get("PIPELINE_GROQ_WORKLOAD_LANGUAGE") == expected
    assert os.environ["PIPELINE_GROQ_WORKLOAD_LANGUAGE"] == "es"
