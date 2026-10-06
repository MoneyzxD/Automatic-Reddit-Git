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
import json
import math
import re
import time
import threading

from utils import telemetry

logger = logging.getLogger(__name__)

# A cota é da organização, não da chave. Compartilhar por modelo é conservador
# quando idiomas usam contas distintas, mas evita presumir que chaves diferentes
# significam cotas independentes. Estado só deste processo; não coordena outros
# consumidores da organização. Não substitui o retry limitado do guardião.
_NEXT_REQUEST_AT: dict[str, float] = {}
_CADENCE_LOCK = threading.Lock()
_TOKEN_RESET_RE = re.compile(r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?")

_DIAGNOSTIC_INTS = (
    "payload_bytes", "payload_chars", "completion_cap", "legacy_cap",
    "limit_tpm", "remaining_tpm", "limit_rpd", "remaining_rpd",
    "prompt", "completion", "total", "http_status",
)
_DIAGNOSTIC_SECONDS = ("reset_tpm_seconds", "reset_rpd_seconds", "retry_after_seconds")
_DIAGNOSTIC_DURATION = re.compile(
    r"(?:(\d+(?:\.\d+)?)d)?(?:(\d+(?:\.\d+)?)h)?"
    r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?")


def sanitize_groq_diagnostic(value):
    """Só números limitados: nunca transportar corpo, cabeçalhos livres ou nomes."""
    if not isinstance(value, dict):
        return None
    diagnostic = {}
    for key in _DIAGNOSTIC_INTS:
        item = value.get(key)
        valid = type(item) is int and 0 <= item <= 10**9
        if key == "http_status":
            valid = valid and 100 <= item <= 599
        diagnostic[key] = item if valid else None
    for key in _DIAGNOSTIC_SECONDS:
        item = value.get(key)
        diagnostic[key] = (item if type(item) in {int, float} and 0 <= item <= 604800
                           and math.isfinite(item) else None)
    return diagnostic


def _header_number(headers, name, *, seconds=False):
    value = headers.get(name, "") if headers else ""
    pattern = r"[0-9]{1,7}(?:\.[0-9]{1,9})?" if seconds else r"[0-9]{1,10}"
    if isinstance(value, str) and re.fullmatch(pattern, value):
        number = float(value) if seconds else int(value)
        if number <= (604800 if seconds else 10**9):
            return number
    return None


def _diagnostic_reset(headers, name):
    value = headers.get(name, "") if headers else ""
    match = _DIAGNOSTIC_DURATION.fullmatch(value) if isinstance(value, str) and len(value) <= 64 else None
    if match and any(match.groups()):
        seconds = sum(float(part or 0) * unit for part, unit in zip(match.groups(), (86400, 3600, 60, 1)))
        if math.isfinite(seconds) and 0 <= seconds <= 604800:
            return seconds
    return None


def _emit_http_diagnostic(response=None, *, request=None, usage=None, exc=None):
    """Observação best-effort; não modifica a requisição, o retorno ou o retry."""
    try:
        headers = getattr(response, "headers", None)
        diagnostic = {
            "http_status": getattr(response, "status_code", None),
            "limit_tpm": _header_number(headers, "x-ratelimit-limit-tokens"),
            "remaining_tpm": _header_number(headers, "x-ratelimit-remaining-tokens"),
            "limit_rpd": _header_number(headers, "x-ratelimit-limit-requests"),
            "remaining_rpd": _header_number(headers, "x-ratelimit-remaining-requests"),
            "reset_tpm_seconds": _diagnostic_reset(headers, "x-ratelimit-reset-tokens"),
            "reset_rpd_seconds": _diagnostic_reset(headers, "x-ratelimit-reset-requests"),
            "retry_after_seconds": _header_number(headers, "retry-after", seconds=True),
            "prompt": getattr(usage, "prompt_tokens", None),
            "completion": getattr(usage, "completion_tokens", None),
            "total": getattr(usage, "total_tokens", None),
        }
        request = request if request is not None else getattr(response, "request", None)
        try:
            # Não chamar read(): corpos ainda não carregados/streams permanecem intactos.
            body = getattr(request, "content", None)
            if isinstance(body, bytes):
                diagnostic["payload_bytes"] = len(body)
                if len(body) <= 1048576:
                    text = body.decode("utf-8")
                    diagnostic["payload_chars"] = len(text)
                    payload = json.loads(text)
                    if isinstance(payload, dict):
                        diagnostic["completion_cap"] = payload.get("max_completion_tokens")
                        diagnostic["legacy_cap"] = payload.get("max_tokens")
        except (ValueError, AttributeError, RuntimeError):
            pass
        diagnostic = sanitize_groq_diagnostic(diagnostic)
        if exc is not None:
            # Somente esta tentativa: não há estado global de último diagnóstico.
            exc.groq_diagnostic = diagnostic
        logger.info("Diagnóstico HTTP Groq: %s", json.dumps(diagnostic, allow_nan=False))
    except Exception:
        # Diagnóstico não pode mascarar o resultado nem a exceção original.
        pass


def _token_reset_seconds(headers) -> float:
    """Lê só a recarga TPM; reset-requests é diário e não serve para cadência."""
    value = headers.get("x-ratelimit-reset-tokens", "") if headers else ""
    match = _TOKEN_RESET_RE.fullmatch(value) if isinstance(value, str) and len(value) <= 40 else None
    if match and any(match.groups()):
        seconds = float(match[1] or 0) * 60 + float(match[2] or 0)
        if 0 <= seconds <= 120:
            # Os GPT-OSS atuais do plano gratuito também têm teto de 30 RPM.
            # O cabeçalho de requests é RPD, não informa esse teto por minuto.
            return min(max(seconds + 1.0, 2.1), 120.0)  # margem e teto de espera
    # Sem informação confiável, uma janela completa após a tentativa, mesmo
    # rejeitada: a geração de um JSON inválido também pode consumir tokens.
    return 61.0


def _paced_create(inner, stage, model, args, kwargs):
    with _CADENCE_LOCK:
        remaining = _NEXT_REQUEST_AT.get(model, 0) - time.monotonic()
        if remaining > 0:
            logger.info("Cadência Groq (%s): aguardando %.1fs pela recarga TPM", stage, remaining)
        while remaining > 0:
            time.sleep(min(remaining, 60.0))
            remaining = _NEXT_REQUEST_AT.get(model, 0) - time.monotonic()
        headers = None
        try:
            raw_api = getattr(inner, "with_raw_response", None)
            if raw_api is not None and not kwargs.get("stream"):
                raw = raw_api.create(*args, **kwargs)
                headers = raw.headers
                result = raw.parse()
                _emit_http_diagnostic(getattr(raw, "http_response", None), usage=getattr(result, "usage", None))
                return result
            result = inner.create(*args, **kwargs)
            _emit_http_diagnostic(usage=None if kwargs.get("stream") else getattr(result, "usage", None))
            return result
        except Exception as exc:
            response = getattr(exc, "response", None)
            headers = getattr(response, "headers", None)
            _emit_http_diagnostic(response, request=getattr(exc, "request", None), exc=exc)
            raise
        finally:
            _NEXT_REQUEST_AT[model] = time.monotonic() + _token_reset_seconds(headers)

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
# Observado em producao de duas formas: travessoes/aspas curvas viram "â" +
# controle C1 invisivel (\x80-\x9f, do em-dash E2 80 94), E acentuacao
# pt/es vira "Ã±", "Ã­", "Ã³" etc. (do "n" 0xC3 0xB1 etc.) — ambos o mesmo
# padrao raiz: bytes UTF-8 validos decodificados como Latin-1 em algum
# ponto entre a resposta do Groq e o texto chegar aqui. A primeira versao
# deste reparo so cobria o primeiro caso (regex restrita a \x80-\x9f) — a
# acentuacao pt/es usa bytes fora dessa faixa (0xA0-0xFF) e passava direto,
# o que e MUITO mais grave pra esses dois idiomas (toda palavra acentuada).
#
# Deteccao generica: qualquer texto com caractere nao-ASCII e candidato.
# Reencodar como Latin-1 (sempre reversivel para codepoints 0-255) recupera
# os bytes originais; decodificar como UTF-8 reconstroi o caractere certo.
# Texto legitimamente acentuado (ja correto) nao sofre nada — um "ñ" real
# e um UNICO codepoint que nao forma sequencia UTF-8 valida sozinho, entao
# o round-trip falha com UnicodeDecodeError e o texto original e mantido.
def _reparar_mojibake(texto: str) -> str:
    if not texto or texto.isascii():
        return texto
    try:
        reparado = texto.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return texto
    return reparado if reparado != texto else texto


class _TrackedCompletions:
    """Proxy de client.chat.completions que contabiliza uso apos cada create()."""

    def __init__(self, inner, stage: str, *, retry_rate_limit: bool = True):
        self._inner = inner
        self._stage = stage
        self._retry_rate_limit = retry_rate_limit

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
                resp = _paced_create(self._inner, self._stage, modelo, args, kwargs)
                break
            except Exception as e:
                if self._retry_rate_limit and _e_rate_limit(e) and tentativa < _RATE_LIMIT_MAX_TENTATIVAS:
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
    def __init__(self, inner, stage: str, *, retry_rate_limit: bool = True):
        self._inner = inner
        self.completions = _TrackedCompletions(inner.completions, stage, retry_rate_limit=retry_rate_limit)

    def __getattr__(self, name):
        return getattr(self._inner, name)


class TrackedGroq:
    """Wrapper de Groq com contabilidade de tokens por estagio."""

    def __init__(self, api_key: str, stage: str, *, sdk_max_retries: int | None = None,
                 retry_rate_limit: bool = True, timeout: float | None = None):
        from groq import Groq
        options = {"api_key": api_key}
        if sdk_max_retries is not None:
            options["max_retries"] = sdk_max_retries
        if timeout is not None:
            options["timeout"] = timeout
        self._client = Groq(**options)
        self.chat = _TrackedChat(self._client.chat, stage, retry_rate_limit=retry_rate_limit)

    def __getattr__(self, name):
        return getattr(self._client, name)


def tracked_groq(api_key: str, stage: str, *, sdk_max_retries: int | None = None,
                 retry_rate_limit: bool = True, timeout: float | None = None) -> TrackedGroq:
    """Cria um cliente Groq instrumentado para o estagio informado."""
    return TrackedGroq(api_key, stage, sdk_max_retries=sdk_max_retries,
                       retry_rate_limit=retry_rate_limit, timeout=timeout)
