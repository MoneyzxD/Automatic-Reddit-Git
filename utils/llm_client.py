"""Seleciona o cliente de IA sem alterar os contratos das etapas existentes."""

from utils import environment as env


def tracked_llm(api_key: str, stage: str, **options):
    """Um provedor fixo; rollback explícito conserva o cliente Groq original."""
    if env.llm_provider() == "gemini":
        from utils.gemini_client import GeminiClient
        return GeminiClient(api_key, stage, **options)
    from utils.groq_client import tracked_groq
    return tracked_groq(api_key, stage, **options)
