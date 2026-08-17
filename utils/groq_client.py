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

from utils import telemetry

logger = logging.getLogger(__name__)


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

        resp = self._inner.create(*args, **kwargs)
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
