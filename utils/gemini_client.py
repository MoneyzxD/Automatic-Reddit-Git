"""Gemini REST gratuito com o contrato textual usado pelas etapas do pipeline.

Não instala SDK novo nem alterna modelos/chaves por cota. A modalidade gratuita
depende do projeto Google sem faturamento; a API não informa o plano da chave.
"""

from __future__ import annotations

import logging
import math
import os
import re
import threading
import time
from types import SimpleNamespace

import requests

from utils import telemetry

logger = logging.getLogger(__name__)
_LOCK = threading.Lock()
_NEXT_REQUEST_AT: dict[str, float] = {}
# Catálogo confirmado na documentação oficial; não inclui modelos só pagos.
_FREE_MODELS = {"gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.8-flash"}


class GeminiError(RuntimeError):
    """Somente código/status e espera numérica; nunca corpo, prompt ou chave."""

    def __init__(self, code: str, status: int | None = None, wait: float | None = None):
        super().__init__(f"Gemini indisponível: {code}; HTTP={status}")
        self.status_code = status
        self.body = {"error": {"code": code}}
        self.response = SimpleNamespace(headers={"retry-after": str(wait)} if wait is not None else {})


def _retry_seconds(headers, body):
    """RetryInfo tipificado ou Retry-After numérico, nunca a mensagem livre."""
    waits = []
    header = next((value for key, value in headers.items() if key.lower() == "retry-after"), None)
    if isinstance(header, str) and re.fullmatch(r"\d{1,7}(?:\.\d{1,9})?", header):
        waits.append(float(header))
    error = body.get("error", {}) if isinstance(body, dict) else {}
    details = error.get("details", []) if isinstance(error, dict) else []
    for item in details if isinstance(details, list) else []:
        if not isinstance(item, dict) or item.get("@type") != "type.googleapis.com/google.rpc.RetryInfo":
            continue
        delay = item.get("retryDelay")
        if isinstance(delay, str) and re.fullmatch(r"\d{1,7}(?:\.\d{1,9})?s", delay):
            waits.append(float(delay[:-1]))
    return max(waits) if waits else None


def _tokens(metadata, field):
    value = metadata.get(field, 0)
    return value if type(value) is int and 0 <= value <= 10**9 else 0


class GeminiClient:
    def __init__(self, api_key, stage, *, sdk_max_retries=None, retry_rate_limit=True, timeout=None):
        if not isinstance(api_key, str) or not api_key.strip():
            raise GeminiError("invalid_api_key", 401)
        self.model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash").strip()
        if self.model not in _FREE_MODELS:
            raise ValueError("Modelo Gemini sem modalidade gratuita validada")
        self.timeout = 60.0 if timeout is None else timeout
        self.interval = float(os.getenv("GEMINI_MIN_INTERVAL_SECONDS", "13"))
        if (type(self.timeout) not in {int, float} or not math.isfinite(self.timeout) or self.timeout <= 0
                or not math.isfinite(self.interval) or not 0 <= self.interval <= 120):
            raise ValueError("Limites de requisição Gemini inválidos")
        self._api_key = api_key
        self._stage = stage
        # O guardião é dono do seu próprio retry; não empilhar tentativas de SDK.
        self._attempts = 2 if retry_rate_limit and sdk_max_retries != 0 else 1
        self.chat = SimpleNamespace(completions=self)

    def create(self, *, messages, model=None, max_tokens=None, max_completion_tokens=None,
               temperature=None, response_format=None, reasoning_effort=None):
        """Traduz só a interface usada pelo projeto; Gemini escolhe seu modelo fixo."""
        config = {"thinkingConfig": {"thinkingBudget": 0} if self.model.startswith("gemini-2.5-")
                  else {"thinkingLevel": "low"}}
        cap = max_completion_tokens if max_completion_tokens is not None else max_tokens
        if cap is not None:
            config["maxOutputTokens"] = cap
        # Gemini 3.6+ ignora temperatura e anuncia futura rejeição do parâmetro.
        if temperature is not None and self.model.startswith("gemini-2.5-"):
            config["temperature"] = temperature
        if response_format:
            kind = response_format.get("type")
            if kind not in {"json_schema", "json_object"}:
                raise ValueError("Formato Gemini não suportado")
            config["responseMimeType"] = "application/json"
            if kind == "json_schema":
                config["responseJsonSchema"] = response_format["json_schema"]["schema"]
        contents, instructions = [], []
        for message in messages:
            content = message["content"]
            if not isinstance(content, str):
                raise ValueError("Gemini aceita somente mensagens de texto neste pipeline")
            role = message["role"]
            if role == "system":
                instructions.append({"text": content})
            elif role in {"user", "assistant"}:
                contents.append({"role": "user" if role == "user" else "model", "parts": [{"text": content}]})
            else:
                raise ValueError("Papel de mensagem Gemini não suportado")
        payload = {"contents": contents, "generationConfig": config}
        if instructions:
            payload["systemInstruction"] = {"parts": instructions}
        for attempt in range(self._attempts):
            try:
                data = self._post(payload)
            except (TimeoutError, ConnectionError) as error:
                if attempt + 1 == self._attempts:
                    raise
                logger.warning("Falha transitória Gemini (%s): %s; segunda tentativa em 15s",
                               self._stage, type(error).__name__)
                _sleep(15)
            except GeminiError as error:
                wait = _retry_seconds(error.response.headers, {})
                if error.status_code not in {429, 503} or attempt + 1 == self._attempts or (wait is not None and wait > 30):
                    raise
                _sleep(15 if wait is None else wait)
            else:
                return self._response(data)

    def _post(self, payload):
        # Cadência compartilhada entre etapas/idiomas neste processo. Não promete
        # disponibilidade diária nem coordena consumidores externos do projeto.
        with _LOCK:
            remaining = _NEXT_REQUEST_AT.get(self.model, 0) - time.monotonic()
            if remaining > 0:
                logger.info("Cadência Gemini (%s): aguardando %.1fs", self._stage, remaining)
                _sleep(remaining)
            response = None
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent",
                    headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                    json=payload, timeout=self.timeout, allow_redirects=False,
                )
                try:
                    data = response.json()
                except ValueError:
                    data = None
                if response.status_code != 200:
                    wait = _retry_seconds(response.headers, data)
                    raise GeminiError("resource_exhausted" if response.status_code == 429 else "provider_error",
                                      response.status_code, wait)
                if not isinstance(data, dict):
                    raise GeminiError("invalid_json")
                return data
            except requests.Timeout:
                raise TimeoutError("Tempo de requisição Gemini esgotado") from None
            except requests.RequestException:
                raise ConnectionError("Conexão Gemini indisponível") from None
            finally:
                _NEXT_REQUEST_AT[self.model] = time.monotonic() + self.interval
                if response is not None:
                    response.close()

    def _response(self, data):
        metadata = data.get("usageMetadata", {})
        metadata = metadata if isinstance(metadata, dict) else {}
        usage = SimpleNamespace(prompt_tokens=_tokens(metadata, "promptTokenCount"),
                                completion_tokens=_tokens(metadata, "candidatesTokenCount") + _tokens(metadata, "thoughtsTokenCount"),
                                total_tokens=_tokens(metadata, "totalTokenCount"))
        telemetry.record_usage(self._stage, self.model, usage)
        candidates = data.get("candidates")
        candidate = candidates[0] if isinstance(candidates, list) and len(candidates) == 1 else None
        if not isinstance(candidate, dict) or candidate.get("finishReason") != "STOP":
            raise GeminiError("incomplete_response")
        content = candidate.get("content", {})
        parts = content.get("parts", []) if isinstance(content, dict) else []
        if not isinstance(parts, list):
            raise GeminiError("incomplete_response")
        text = "".join(part["text"] for part in parts if isinstance(part, dict)
                       and not part.get("thought") and isinstance(part.get("text"), str))
        if not text.strip():
            raise GeminiError("incomplete_response")
        logger.info("Resposta Gemini concluída (%s, modelo=%s, tokens=%d)",
                    self._stage, self.model, usage.total_tokens)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=text), finish_reason="stop")], usage=usage)


def _sleep(seconds):
    """Esperas limitadas em blocos para conservar o processo responsivo."""
    while seconds > 0:
        step = min(seconds, 60)
        time.sleep(step)
        seconds -= step
