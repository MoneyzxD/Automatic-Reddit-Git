"""Regeneração com feedback, sem consultar provedores reais."""
import json
from types import SimpleNamespace

from stages.naturalizer import ScriptNaturalizer


def test_feedback_e_fonte_chegam_ao_provedor_sem_alterar_perfil(monkeypatch):
    from utils import environment, llm_client
    calls = []
    monkeypatch.setattr(environment, "llm_api_key", lambda *args: "chave-sintetica")
    monkeypatch.setattr(environment, "llm_provider", lambda: "groq")
    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Texto corrigido."))])
    monkeypatch.setattr(llm_client, "tracked_llm", lambda *args: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    feedback = {"rejected_text": "Cada um valia 150 dólares.", "issues": [
        {"category": "grammar", "original": "um valia", "message": "Concordância."}]}
    assert ScriptNaturalizer({})._groq_rewrite("Fonte aprovada.", "pt", "male",
        retry_feedback=feedback) == "Texto corrigido."
    prompt = calls[0]["messages"][1]["content"]
    assert json.dumps(feedback, ensure_ascii=False) in prompt
    assert "Fonte aprovada." in prompt and "NARRADOR — MASCULINO" in prompt
    assert "nova revisão obrigatória" in prompt


def test_feedback_e_preservado_em_todos_os_lotes(monkeypatch):
    calls = []
    def rewrite(self, text, language, gender, **kwargs):
        calls.append((text, language, gender, kwargs))
        return text
    monkeypatch.setattr(ScriptNaturalizer, "_groq_rewrite", rewrite)
    text = "a" * 3100 + "\n\n" + "b" * 3100
    feedback = {"rejected_text": "Antes", "issues": []}
    assert ScriptNaturalizer({}).naturalize(text, "pt", "female", retry_feedback=feedback) == text
    assert len(calls) == 2
    assert all(c[1:3] == ("pt", "female") and c[3]["retry_feedback"] == feedback for c in calls)
