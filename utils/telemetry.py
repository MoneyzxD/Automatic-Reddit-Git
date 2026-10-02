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
import json
import os
import re
from http.cookies import SimpleCookie, CookieError
from pathlib import Path
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


def append_quality_report(path: Path, event: dict) -> None:
    """Acrescenta um evento sanitizado sem substituir linhas anteriores."""
    secret_names = ("token", "secret", "cookie", "authorization", "api_key", "api-key",
                    "credentials", "password", "passwd")
    def sensitive(key):
        return any(word in key.lower() for word in secret_names)

    configured = set()
    def collect_json(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if sensitive(key) and isinstance(item, str) and item:
                    configured.add(item)
                else:
                    collect_json(item)
        elif isinstance(value, list):
            for item in value:
                collect_json(item)

    for key, value in os.environ.items():
        if not sensitive(key) or not value.strip():
            continue
        normalized = value.strip().strip('"').strip("'")
        configured.update((value, normalized))
        try:
            collect_json(json.loads(normalized))
        except ValueError:
            pass
        if "cookie" in key.lower():
            try:
                cookies = SimpleCookie()
                cookies.load(normalized)
                configured.update(item.value for item in cookies.values() if item.value)
            except CookieError:
                pass
    configured.discard("")
    configured_values = sorted(configured, key=len, reverse=True)
    headers = re.compile(r"(?im)(\b(?:cookie|set-cookie|authorization|proxy-authorization)\s*:\s*)[^\r\n]+")
    assignments = re.compile(
        r'''(?i)(\b[\w-]*(?:api[_-]?key|token|secret|cookie|authorization|credentials|password|passwd|reddit_session)[\w-]*["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|(?:Bearer|Basic)\s+[^\s,;}&]+|[^\s,;}&]+)'''
    )

    def redact(value, key=""):
        # Os hashes auditam o original: nunca recalcular nem sanitizar seus dígitos.
        if key in {"source_sha256", "candidate_sha256"} and isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value):
            return value
        if sensitive(key):
            return "[REDACTED]"
        if isinstance(value, dict):
            return {key: redact(item, str(key)) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [redact(item) for item in value]
        if isinstance(value, str):
            for secret in configured_values:
                value = value.replace(secret, "[REDACTED]")
            value = headers.sub(r"\1[REDACTED]", value)
            value = assignments.sub(r"\1[REDACTED]", value)
            value = re.sub(r"(?i)(\bBearer\s+)[-A-Za-z0-9._~+/]+=*", r"\1[REDACTED]", value)
            return re.sub(r"(https?://api\.telegram\.org/bot)\d+:[A-Za-z0-9_-]+", r"\1[REDACTED]", value)
        return value

    line = json.dumps(redact(event), ensure_ascii=False) + "\n"
    # ponytail: lock por processo; usar escritor único se houver revisões multiprocesso concorrentes.
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line)


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
