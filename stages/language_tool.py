"""Cliente HTTP para uma instância local do LanguageTool."""

from dataclasses import dataclass
import os
from urllib.parse import urlsplit, urlunsplit

import requests


@dataclass(frozen=True)
class LanguageIssue:
    rule_id: str
    category: str
    message: str
    replacements: tuple[str, ...]
    start: int
    end: int
    original: str


@dataclass(frozen=True)
class HealthReport:
    version: str
    locales: tuple[str, ...]


class LanguageToolUnavailable(RuntimeError):
    """A instância local falhou ou devolveu uma resposta inválida."""


class _TransportUnavailable(LanguageToolUnavailable):
    """Falha de conexão ou HTTP do servidor local."""


def _utf16_index_to_python(text: str, utf16_index: int) -> int:
    if type(utf16_index) is not int or utf16_index < 0:
        raise ValueError("offset UTF-16 inválido")
    consumed = 0
    for index, char in enumerate(text):
        if consumed == utf16_index:
            return index
        consumed += 2 if ord(char) > 0xFFFF else 1
        if consumed > utf16_index:
            raise ValueError("offset UTF-16 dentro de um caractere")
    if consumed == utf16_index:
        return len(text)
    raise ValueError("offset UTF-16 fora do texto")


def _endpoints(url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path.rstrip("/") not in {"/v2", "/v2/check"}
        ):
            raise ValueError("URL não aponta para LanguageTool local")
        _ = parsed.port
    except (TypeError, ValueError) as exc:
        raise LanguageToolUnavailable("URL do LanguageTool local inválida") from exc
    base = urlunsplit(("http", parsed.netloc, "/v2", "", ""))
    return f"{base}/check", f"{base}/languages"


def _json(response):
    if 300 <= response.status_code < 400:
        raise LanguageToolUnavailable("Redirecionamento recusado pelo LanguageTool local")
    try:
        response.raise_for_status()
        return response.json()
    except ValueError as exc:
        raise LanguageToolUnavailable("Resposta JSON inválida do LanguageTool") from exc


class LanguageToolClient:
    def __init__(self, config: dict, session: requests.Session | None = None):
        self._config = config
        self._session = session if session is not None else requests.Session()
        self._required = config.get("languagetool_required", True)
        self._timeout = float(config.get("languagetool_timeout_seconds", 15))
        self._languages = config.get("languagetool_languages", {"pt": "pt-BR", "en": "en-US", "es": "es"})
        self._check_url, self._languages_url = _endpoints(
            os.environ.get("LANGUAGETOOL_URL") or config.get("languagetool_url", "http://127.0.0.1:8081/v2/check")
        )
        host = urlsplit(self._check_url).hostname
        self._direct_proxies = {
            "http": None,
            "https": None,
            "all": None,
            f"http://{host}": None,
            f"all://{host}": None,
        }
        self._health_report: HealthReport | None = None

    def _post(self, text: str, locale: str):
        return self._session.post(
            self._check_url,
            data={"text": text, "language": locale},
            timeout=self._timeout,
            allow_redirects=False,
            proxies=self._direct_proxies.copy(),
        )

    def check(self, text: str, language: str) -> tuple[LanguageIssue, ...]:
        key = "pt" if language.lower() == "pt-br" else language.lower()
        if key not in self._languages:
            raise ValueError(f"Idioma desconhecido: {language}")
        if self._health_report is None:
            try:
                self._health_report = self.health()
            except _TransportUnavailable:
                if not self._required:
                    return ()
                raise
        try:
            payload = _json(self._post(text, self._languages[key]))
        except (requests.RequestException, OSError) as exc:
            if not self._required:
                return ()
            raise LanguageToolUnavailable("LanguageTool local indisponível") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("matches"), list):
            raise LanguageToolUnavailable("Resposta de revisão inválida do LanguageTool")

        issues = []
        for match in payload["matches"]:
            try:
                offset = match["offset"]
                length = match["length"]
                if type(offset) is not int or type(length) is not int or length < 0:
                    raise ValueError("span UTF-16 inválido")
                start = _utf16_index_to_python(text, offset)
                end = _utf16_index_to_python(text, offset + length)
                message = match["message"]
                replacements = tuple(item["value"] for item in match["replacements"])
                rule = match["rule"]
                rule_id = rule["id"]
                category = rule["category"]["id"]
                if (
                    not isinstance(message, str)
                    or not isinstance(match["replacements"], list)
                    or any(not isinstance(value, str) for value in replacements)
                    or not isinstance(rule_id, str)
                    or not isinstance(category, str)
                ):
                    raise ValueError("campos de revisão inválidos")
            except (TypeError, KeyError, ValueError) as exc:
                raise LanguageToolUnavailable("Achado inválido do LanguageTool") from exc
            issues.append(LanguageIssue(rule_id, category, message, replacements, start, end, text[start:end]))
        return tuple(issues)

    def health(self, expected_version: str = "6.6") -> HealthReport:
        try:
            languages = _json(self._session.get(
                self._languages_url,
                timeout=self._timeout,
                allow_redirects=False,
                proxies=self._direct_proxies.copy(),
            ))
            check = _json(self._post("ok", "en-US"))
        except (requests.RequestException, OSError) as exc:
            raise _TransportUnavailable("LanguageTool local indisponível") from exc

        try:
            if not isinstance(languages, list) or not isinstance(check, dict):
                raise ValueError("resposta de saúde inválida")
            locales = tuple(item["longCode"] for item in languages)
            if any(not isinstance(locale, str) for locale in locales):
                raise ValueError("locale inválido")
            version = check["software"]["version"]
            if not isinstance(version, str) or version != expected_version:
                raise ValueError("versão incorreta")
            if not {"pt-BR", "en-US", "es"}.issubset(locales):
                raise ValueError("locale obrigatório ausente")
            if not isinstance(check.get("matches"), list):
                raise ValueError("resposta de verificação inválida")
        except (TypeError, KeyError, ValueError) as exc:
            raise LanguageToolUnavailable("Health check do LanguageTool falhou") from exc
        return HealthReport(version, locales)
