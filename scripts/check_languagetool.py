"""Confirma e aquece o LanguageTool local usando apenas a biblioteca padrão."""

import argparse
from dataclasses import dataclass
import json
import math
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener


class HealthCheckFailed(RuntimeError):
    """O runtime local não satisfaz o contrato de saúde."""


@dataclass(frozen=True)
class HealthReport:
    version: str
    locales: tuple[str, ...]


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class _Requester:
    def __init__(self):
        self.opener = build_opener(ProxyHandler({}), _NoRedirect())

    def _json(self, request, timeout):
        with self.opener.open(request, timeout=timeout) as response:
            try:
                return json.load(response)
            except (ValueError, UnicodeError) as exc:
                raise HealthCheckFailed("Resposta JSON inválida do LanguageTool") from exc

    def get_json(self, url, timeout):
        return self._json(Request(url), timeout)

    def post_form_json(self, url, data, timeout):
        return self._json(Request(url, data=urlencode(data).encode("utf-8")), timeout)


def _base_url(url):
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") not in {"", "/v2", "/v2/check"}
            or (parsed.port is not None and parsed.port < 1)
        ):
            raise ValueError()
        return urlunsplit(("http", parsed.netloc, "/v2", "", ""))
    except (TypeError, ValueError) as exc:
        raise HealthCheckFailed("URL do LanguageTool local inválida") from exc


def wait_until_ready(base_url, expected_version, required_locales, timeout_seconds, *, requester=None):
    base = _base_url(base_url)
    if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise HealthCheckFailed("Prazo de saúde inválido")
    required = tuple(required_locales)
    sentences = {"pt-BR": "Esta é uma frase de teste.", "en-US": "This is a test sentence.", "es": "Esta es una frase de prueba."}
    if not required or any(locale not in sentences for locale in required):
        raise HealthCheckFailed("Locale de aquecimento inválido")
    transport = requester if requester is not None else _Requester()
    deadline = time.monotonic() + timeout_seconds

    def remaining():
        seconds = deadline - time.monotonic()
        if seconds <= 0:
            raise HealthCheckFailed("LanguageTool indisponível no prazo de aquecimento")
        return min(15, seconds)

    while True:
        try:
            languages = transport.get_json(f"{base}/languages", timeout=remaining())
            if not isinstance(languages, list) or any(
                not isinstance(item, dict) or not isinstance(item.get("longCode"), str)
                for item in languages
            ):
                raise HealthCheckFailed("Resposta de locales inválida do LanguageTool")
            locales = tuple(item["longCode"] for item in languages)
            if not set(required).issubset(locales):
                raise HealthCheckFailed("Locale obrigatório ausente no LanguageTool")
            for locale in required:
                payload = transport.post_form_json(
                    f"{base}/check", {"text": sentences[locale], "language": locale}, timeout=remaining()
                )
                if not isinstance(payload, dict) or not isinstance(payload.get("software"), dict) or not isinstance(payload.get("matches"), list):
                    raise HealthCheckFailed("Resposta de aquecimento inválida do LanguageTool")
                if payload["software"].get("version") != expected_version:
                    raise HealthCheckFailed("Versão incorreta do LanguageTool")
            remaining()
            return HealthReport(expected_version, locales)
        except HTTPError as exc:
            if exc.code not in {408, 425, 429, 500, 502, 503, 504}:
                raise HealthCheckFailed(f"HTTP {exc.code} recusado pelo LanguageTool local") from exc
        except (URLError, OSError):
            pass
        time.sleep(min(0.5, remaining()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-version", required=True)
    parser.add_argument("--required-locales", nargs="+", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=120)
    args = parser.parse_args()
    try:
        report = wait_until_ready(args.url, args.expected_version, args.required_locales, args.timeout_seconds)
    except HealthCheckFailed as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(f"LanguageTool {report.version} pronto; idiomas aquecidos: {', '.join(args.required_locales)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
