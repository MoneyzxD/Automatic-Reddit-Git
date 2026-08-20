"""
utils/groq_client.py
====================
Cliente Groq instrumentado.

Substitui `Groq(api_key=...)` nos estagios por um proxy que registra
automaticamente o consumo de tokens em utils/telemetry.py. A interface e
identica — `client.chat.completions.create(...)` funciona igual e devolve o
mesmo objeto de resposta — entao nenhum estagio precisa mudar sua logica,
so a linha de criacao do cliente.

Motivo: sem isso, so o validator contabilizava tokens. Os estagios de
geracao (naturalizer no modelo grande, titler, adapter, metadata) eram
invisiveis no orcamento de TPM, o que impedia responder com numero se o
volume-alvo cabe no free tier.
"""
from __future__ import annotations

import logging
import re
import time

from utils import telemetry

logger = logging.getLogger(__name__)

# ── RETRY EM RATE LIMIT (429) ────────────────────────────────────────────────
# O SDK do Groq ja tenta de novo sozinho algumas vezes, mas desiste antes do
# TPM liberar — a API costuma pedir poucos segundos ("Please try again in
# 8.01s"), bem menos do que o tempo ja gasto nas tentativas anteriores. Sem isto, um
# 429 isolado (comum quando varios checkpoints de validacao caem no mesmo
# minuto) derruba o estagio inteiro para o fallback sem-LLM, mesmo quando
# esperar poucos segundos teria resolvido com qualidade plena.
_RATE_LIMIT_MAX_TENTATIVAS = 2
_RATE_LIMIT_ESPERA_TETO    = 30.0
_RATE_LIMIT_ESPERA_PADRAO  = 15.0
_RETRY_AFTER_RE = re.compile(r"try again in ([\d.]+)s", re.IGNORECASE)


def _e_rate_limit(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    texto = str(exc).lower()
    return "rate_limit" in texto or "429" in texto


def _espera_sugerida(exc: Exception) -> float:
    m = _RETRY_AFTER_RE.search(str(exc))
    if m:
        try:
            return min(float(m.group(1)), _RATE_LIMIT_ESPERA_TETO)
        except ValueError:
            pass
    return _RATE_LIMIT_ESPERA_PADRAO


#: Modelos de raciocinio que aceitam reasoning_effort. Neles, o "pensamento"
#: consome o orcamento de max_tokens ANTES de escrever a resposta — com
#: orcamento apertado (JSON do validator, descricao de 150 tokens do
#: metadata) o raciocinio come tudo e o conteudo volta VAZIO, derrubando o
#: estagio para fallback silenciosamente. Medido: effort=low entrega saida
#: identica gastando 1/3 dos tokens (154 vs 473 no mesmo prompt).
_MODELOS_COM_RACIOCINIO = ("gpt-oss", "qwen3", "o1", "o3")

_REASONING_EFFORT_PADRAO = "low"


def _aceita_reasoning_effort(model: str) -> bool:
    m = (model or "").lower()
    return any(marca in m for marca in _MODELOS_COM_RACIOCINIO)


# ── REPARO DE MOJIBAKE (UTF-8 decodificado como Latin-1) ────────────────────
# Observado em producao: travessoes/aspas curvas que o modelo gera saem como
# "â" seguido de caractere(s) de controle C1 invisiveis (\x80-\x9f) — o
# padrao classico de bytes UTF-8 validos (ex: E2 80 94 do em-dash) que foram
# decodificados como Latin-1 em algum ponto entre a resposta do Groq e o
# texto chegar aqui. C1 (\x80-\x9f) nunca aparece legitimamente em narracao,
# entao a presenca dele e um sinal seguro de corrupcao. Reencodar como
# Latin-1 recupera os bytes originais; decodificar como UTF-8 reconstroi o
# caractere certo. Aplicado aqui (unico ponto por onde toda resposta do Groq
# passa) para proteger todos os estagios, independente de qual gerou o
# texto corrompido.
_MOJIBAKE_RE = re.compile(r"[\x80-\x9f]")


def _reparar_mojibake(texto: str) -> str:
    if not texto or not _MOJIBAKE_RE.search(texto):
        return texto
    try:
        return texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto


class _TrackedCompletions:
    """Proxy de client.chat.completions que contabiliza uso apos cada create()."""

    def __init__(self, inner, stage: str):
        self._inner = inner
        self._stage = stage

    def create(self, *args, **kwargs):
        # Injeta reasoning_effort=low quando o modelo suporta e o chamador
        # nao definiu explicitamente. Sem isso, estagios com max_tokens
        # pequeno recebem conteudo vazio e caem para regras.
        modelo = kwargs.get("model", "")
        if "reasoning_effort" not in kwargs and _aceita_reasoning_effort(modelo):
            kwargs["reasoning_effort"] = _REASONING_EFFORT_PADRAO

        tentativa = 0
        while True:
            try:
                resp = self._inner.create(*args, **kwargs)
                break
            except Exception as e:
                if _e_rate_limit(e) and tentativa < _RATE_LIMIT_MAX_TENTATIVAS:
                    tentativa += 1
                    espera = _espera_sugerida(e)
                    logger.warning(
                        "Rate limit do Groq (%s) — aguardando %.1fs para tentar de novo (%d/%d)",
                        self._stage, espera, tentativa, _RATE_LIMIT_MAX_TENTATIVAS,
                    )
                    time.sleep(espera)
                    continue
                raise

        try:
            for choice in getattr(resp, "choices", None) or []:
                msg = getattr(choice, "message", None)
                conteudo = getattr(msg, "content", None) if msg else None
                if isinstance(conteudo, str):
                    reparado = _reparar_mojibake(conteudo)
                    if reparado != conteudo:
                        logger.warning(
                            "Mojibake reparado na resposta do Groq (%s)", self._stage,
                        )
                        msg.content = reparado
        except Exception as e:  # reparo nunca pode quebrar o pipeline
            logger.debug("Falha ao verificar mojibake (%s): %s", self._stage, e)

        try:
            telemetry.record_usage(
                self._stage,
                kwargs.get("model", ""),
                getattr(resp, "usage", None),
            )
        except Exception as e:  # telemetria nunca pode quebrar o pipeline
            logger.debug("Falha ao registrar telemetria (%s): %s", self._stage, e)
        return resp

    def __getattr__(self, name):
        # Qualquer outro atributo (ex: with_raw_response) passa direto
        return getattr(self._inner, name)


class _TrackedChat:
    def __init__(self, inner, stage: str):
        self._inner = inner
        self.completions = _TrackedCompletions(inner.completions, stage)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TrackedGroq:
    """Wrapper de Groq com contabilidade de tokens por estagio."""

    def __init__(self, api_key: str, stage: str):
        from groq import Groq
        self._client = Groq(api_key=api_key)
        self.chat = _TrackedChat(self._client.chat, stage)

    def __getattr__(self, name):
        return getattr(self._client, name)


def tracked_groq(api_key: str, stage: str) -> TrackedGroq:
    """Cria um cliente Groq instrumentado para o estagio informado."""
    return TrackedGroq(api_key, stage)
