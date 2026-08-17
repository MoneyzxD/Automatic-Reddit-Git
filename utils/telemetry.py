"""
utils/telemetry.py
==================
Contabilidade central de consumo de LLM e de quedas para fallback.

Dois problemas concretos que este modulo resolve:

1. CONSUMO DE TOKENS INVISIVEL
   Ate aqui, so o validator contava tokens (ValidatorEngine.token_usage).
   Os estagios de geracao — inclusive o naturalizer, que usa o modelo
   grande e e o mais caro de todos — nao contavam nada. Sem isso e
   impossivel responder "quantas execucoes cabem em um dia" com numero
   em vez de chute.

2. FALLBACK SILENCIOSO
   Quando a Groq falha (modelo descontinuado, rate limit, rede), cada
   estagio cai para regras/templates e loga como se fosse sucesso. O
   pipeline continua, mas a qualidade despenca sem nenhum aviso. Ja
   aconteceu de verdade: os modelos llama foram descontinuados e o
   pipeline rodou inteiro em regras sem um unico ERROR no log.

Uso:
    from utils import telemetry
    telemetry.reset()                              # inicio da execucao
    telemetry.record_usage("naturalizer", model, usage)
    telemetry.record_fallback("titler", "pt", "todos os LLMs falharam")
    print(telemetry.format_summary())              # fim da execucao
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict

logger = logging.getLogger(__name__)

_lock = threading.Lock()

# Consumo por estagio: {stage: {"prompt": int, "completion": int, "total": int, "calls": int}}
_usage: dict[str, dict[str, int]] = defaultdict(
    lambda: {"prompt": 0, "completion": 0, "total": 0, "calls": 0}
)

# Quedas para fallback: lista de dicts {stage, language, reason}
_fallbacks: list[dict[str, str]] = []

# Modelos efetivamente usados: {stage: modelo}
_models: dict[str, str] = {}


def reset() -> None:
    """Zera os contadores. Chamado no inicio de cada execucao do pipeline."""
    with _lock:
        _usage.clear()
        _fallbacks.clear()
        _models.clear()


def record_usage(stage: str, model: str, usage) -> None:
    """
    Registra o consumo de uma chamada LLM.
    `usage` e o objeto retornado pela API (resp.usage) — tolera None.
    """
    if usage is None:
        return
    with _lock:
        acc = _usage[stage]
        acc["prompt"]     += getattr(usage, "prompt_tokens", 0) or 0
        acc["completion"] += getattr(usage, "completion_tokens", 0) or 0
        acc["total"]      += getattr(usage, "total_tokens", 0) or 0
        acc["calls"]      += 1
        if model:
            _models[stage] = model


def record_fallback(stage: str, language: str = "-", reason: str = "") -> None:
    """
    Registra que um estagio caiu para regras/templates em vez de LLM.
    Isso e degradacao de qualidade — sempre logado como WARNING.
    """
    with _lock:
        _fallbacks.append({"stage": stage, "language": language, "reason": reason})
    logger.warning(
        "[FALLBACK] %s (%s) rodou SEM LLM — qualidade degradada. Motivo: %s",
        stage, language, reason or "nao informado",
    )


# ── CONSULTA ──────────────────────────────────────────────────────────────────

def total_tokens() -> int:
    with _lock:
        return sum(a["total"] for a in _usage.values())


def total_calls() -> int:
    with _lock:
        return sum(a["calls"] for a in _usage.values())


def fallbacks() -> list[dict[str, str]]:
    with _lock:
        return list(_fallbacks)


def had_fallback() -> bool:
    with _lock:
        return bool(_fallbacks)


def usage_by_stage() -> dict[str, dict[str, int]]:
    with _lock:
        return {k: dict(v) for k, v in _usage.items()}


# ── RELATORIOS ────────────────────────────────────────────────────────────────

def format_summary() -> str:
    """Resumo curto para o log e para o Telegram."""
    with _lock:
        if not _usage:
            return "Nenhuma chamada LLM registrada"
        linhas = []
        total = 0
        chamadas = 0
        for stage in sorted(_usage, key=lambda s: -_usage[s]["total"]):
            a = _usage[stage]
            total += a["total"]
            chamadas += a["calls"]
            linhas.append(f"  {stage}: {a['total']} tok / {a['calls']} chamada(s)")
        cabecalho = f"{total} tokens em {chamadas} chamada(s)"
        return cabecalho + "\n" + "\n".join(linhas)


def format_fallback_alert() -> str:
    """
    Mensagem de alerta para o Telegram quando houve queda para fallback.
    Retorna string vazia se nao houve nenhuma.
    """
    with _lock:
        if not _fallbacks:
            return ""
        por_estagio: dict[str, list[str]] = defaultdict(list)
        for f in _fallbacks:
            por_estagio[f["stage"]].append(f["language"])
        linhas = [
            f"  {stage} ({', '.join(sorted(set(langs)))})"
            for stage, langs in sorted(por_estagio.items())
        ]
        motivo = _fallbacks[0].get("reason", "")
        return (
            f"⚠️ Pipeline rodou SEM LLM em {len(por_estagio)} estagio(s)\n"
            f"A qualidade do conteudo esta degradada (regras/templates em vez de LLM).\n\n"
            f"Estagios afetados:\n" + "\n".join(linhas) +
            (f"\n\nPrimeiro motivo: {motivo}" if motivo else "") +
            "\n\nCausa comum: modelo descontinuado pela Groq (404) ou rate limit.\n"
            "Verifique os modelos disponiveis com:\n"
            "python -c \"from groq import Groq; print([m.id for m in Groq().models.list().data])\""
        )
