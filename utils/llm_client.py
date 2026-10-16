"""Seleciona o cliente de IA sem alterar os contratos das etapas existentes."""

from utils import environment as env


class LLMUnavailable(RuntimeError):
    """Geração obrigatória falhou; conservar estado para retomada posterior."""


def require_gemini_result(result, stage: str) -> None:
    """No modo Gemini, falha não aciona outro provedor, regras ou templates."""
    if not result and env.llm_provider() == "gemini":
        raise LLMUnavailable(f"Gemini indisponível na etapa {stage}; geração interrompida")


def tracked_llm(api_key: str, stage: str, **options):
    """Um provedor fixo; rollback explícito conserva o cliente Groq original."""
    if env.llm_provider() == "gemini":
        from utils.gemini_client import GeminiClient
        return GeminiClient(api_key, stage, **options)
    from utils.groq_client import tracked_groq
    return tracked_groq(api_key, stage, **options)
