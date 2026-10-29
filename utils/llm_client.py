"""Seleciona o cliente de IA sem alterar os contratos das etapas existentes."""

from utils import environment as env


class LLMUnavailable(RuntimeError):
    """Geração obrigatória falhou; conservar estado para retomada posterior."""


def propagate_groq_service_failure(error: Exception, stage: str) -> None:
    """Falha real de serviço não pode virar fallback seguido de nova geração."""
    if env.llm_provider() != "groq":
        return
    network_errors, timeout_errors = (TimeoutError,), (TimeoutError,)
    try:
        from groq import APIConnectionError, APITimeoutError
    except ImportError:
        pass
    else:
        network_errors += (APIConnectionError,)
        timeout_errors += (APITimeoutError,)
    status = getattr(error, "status_code", None)
    if (isinstance(error, network_errors) or status == 429
            or type(status) is int and 500 <= status <= 599):
        code = ("rate_limit" if status == 429 else
                "timeout" if isinstance(error, timeout_errors) else "provider_error")
        raise LLMUnavailable(f"Groq indisponível na etapa {stage}: {code}; HTTP={status}") from None


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
