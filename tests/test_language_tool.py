import json
from unittest.mock import Mock

import pytest
import requests
from requests.utils import select_proxy

from stages.language_tool import LanguageIssue, LanguageToolClient, LanguageToolUnavailable


@pytest.fixture(autouse=True)
def sem_url_ambiente(monkeypatch):
    monkeypatch.delenv("LANGUAGETOOL_URL", raising=False)


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise OSError(f"HTTP {self.status_code}")

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


@pytest.fixture
def session():
    fake = Mock()
    fake.get.return_value = FakeResponse([
        {"name": "Portuguese (Brazil)", "code": "pt", "longCode": "pt-BR"},
        {"name": "English (US)", "code": "en", "longCode": "en-US"},
        {"name": "Spanish", "code": "es", "longCode": "es"},
    ])
    fake.post.return_value = FakeResponse({"software": {"version": "6.6"}, "matches": []})
    return fake


def resposta_check(session, payload, status_code=200):
    session.post.side_effect = [
        FakeResponse({"software": {"version": "6.6"}, "matches": []}),
        FakeResponse(payload, status_code),
    ]


def cliente(session, required=True, url="http://127.0.0.1:8081/v2/check"):
    return LanguageToolClient(
        {
            "languagetool_url": url,
            "languagetool_timeout_seconds": 15,
            "languagetool_required": required,
            "languagetool_languages": {"pt": "pt-BR", "en": "en-US", "es": "es"},
        },
        session=session,
    )


class RecordingAdapter(requests.adapters.BaseAdapter):
    def __init__(self):
        self.selected_proxies = []

    def send(self, request, **kwargs):
        self.selected_proxies.append(select_proxy(request.url, kwargs["proxies"]))
        payload = (
            [{"name": "Portuguese (Brazil)", "code": "pt", "longCode": "pt-BR"},
             {"name": "English (US)", "code": "en", "longCode": "en-US"},
             {"name": "Spanish", "code": "es", "longCode": "es"}]
            if request.url.endswith("/languages")
            else {"software": {"version": "6.6"}, "matches": []}
        )
        response = requests.Response()
        response.status_code = 200
        response.url = request.url
        response._content = json.dumps(payload).encode("utf-8")
        return response

    def close(self):
        pass


@pytest.mark.parametrize("injetada", [False, True])
def test_transporte_loopback_ignora_proxies_sem_alterar_sessao(monkeypatch, injetada):
    for variable in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(variable, "http://proxy.invalid:3128")
    for variable in ("NO_PROXY", "no_proxy"):
        monkeypatch.delenv(variable, raising=False)
    session = requests.Session()
    session.proxies = {
        "http": "http://proxy-da-sessao.invalid:3128",
        "http://127.0.0.1": "http://proxy-local-da-sessao.invalid:3128",
    }
    adapter = RecordingAdapter()
    session.mount("http://", adapter)
    proxies_originais = session.proxies.copy()
    if not injetada:
        monkeypatch.setattr("stages.language_tool.requests.Session", lambda: session)

    config = {
        "languagetool_url": "http://127.0.0.1:8081/v2/check",
        "languagetool_languages": {"pt": "pt-BR", "en": "en-US", "es": "es"},
    }
    client = LanguageToolClient(config, session=session if injetada else None)
    assert client.check("Texto", "pt") == ()
    assert adapter.selected_proxies == [None, None, None]
    assert session.proxies == proxies_originais
    assert session.trust_env is True


@pytest.mark.parametrize("version,locales", [
    ("6.5", ["pt-BR", "en-US", "es"]),
    (None, ["pt-BR", "en-US", "es"]),
    ("6.6", ["pt-BR", "en-US"]),
])
@pytest.mark.parametrize("required", [True, False])
def test_check_direto_recusa_versao_ou_locale_invalido(session, version, locales, required):
    session.get.return_value = FakeResponse([
        {"name": code, "code": code.split("-")[0], "longCode": code}
        for code in locales
    ])
    session.post.return_value = FakeResponse({"software": {"version": version}, "matches": []})
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=required).check("Texto", "pt")


def test_check_envia_locale_url_e_timeout(session):
    resposta_check(session, {"matches": []})

    assert cliente(session).check("Eu estou bem.", "pt-br") == ()
    assert session.post.call_count == 2
    args, kwargs = session.post.call_args
    assert args == ("http://127.0.0.1:8081/v2/check",)
    assert kwargs["data"] == {"text": "Eu estou bem.", "language": "pt-BR"}
    assert kwargs["timeout"] == 15.0
    assert kwargs["allow_redirects"] is False
    assert select_proxy(args[0], kwargs["proxies"]) is None


def test_url_base_v2_normaliza_e_usa_locale_es(session):
    resposta_check(session, {"matches": []})

    assert cliente(session, url="http://localhost:8081/v2").check("Hola", "es") == ()
    assert session.post.call_args.args == ("http://localhost:8081/v2/check",)
    assert session.post.call_args.kwargs["data"]["language"] == "es"


def test_override_de_ambiente_prevalece_e_normaliza(session, monkeypatch):
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://[::1]:8081/v2/")
    resposta_check(session, {"matches": []})

    assert cliente(session).check("Hello", "en") == ()
    assert session.post.call_args.args == ("http://[::1]:8081/v2/check",)


@pytest.mark.parametrize("url", [
    "https://127.0.0.1:8081/v2/check",
    "http://example.com/v2/check",
    "http://127.0.0.2:8081/v2/check",
    "http://localhost.example.com/v2/check",
    "http://user@localhost:8081/v2/check",
    "http://localhost:8081/other",
])
def test_url_nao_local_ou_invalida_e_recusada_antes_da_requisicao(session, url):
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False, url=url).check("Texto", "pt")
    session.post.assert_not_called()


def test_override_externo_e_recusado_antes_da_requisicao(session, monkeypatch):
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://example.com/v2")
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")
    session.post.assert_not_called()


def test_locale_desconhecido_e_recusado_antes_da_requisicao(session):
    with pytest.raises(ValueError):
        cliente(session).check("Bonjour", "fr")
    session.post.assert_not_called()


def test_offset_utf16_aponta_para_trecho_python_apos_emoji_composto(session):
    texto = "Oi 👨‍👨‍👦, eu estava cansado."
    # O emoji composto ocupa 8 unidades UTF-16 e 5 posições Python.
    resposta_check(session, {"matches": [{
        "offset": 23,
        "length": 7,
        "message": "Concordância",
        "replacements": [{"value": "cansada"}],
        "rule": {"id": "TEST_GENDER", "category": {"id": "GRAMMAR"}},
    }]})

    assert cliente(session).check(texto, "pt") == (
        LanguageIssue("TEST_GENDER", "GRAMMAR", "Concordância", ("cansada",), 20, 27, "cansado"),
    )


def test_offset_utf16_inclui_emoji_composto_no_trecho(session):
    texto = "A👨‍👨‍👦B"
    resposta_check(session, {"matches": [{
        "offset": 1,
        "length": 8,
        "message": "Teste",
        "replacements": [],
        "rule": {"id": "TEST", "category": {"id": "STYLE"}},
    }]})

    issue = cliente(session).check(texto, "pt")[0]
    assert (issue.start, issue.end, issue.original) == (1, 6, "👨‍👨‍👦")


@pytest.mark.parametrize("offset,length", [(2, 1), (0, 2), (0, 99), (-1, 1)])
def test_span_dentro_de_surrogate_ou_fora_do_texto_e_recusado(session, offset, length):
    resposta_check(session, {"matches": [{
        "offset": offset,
        "length": length,
        "message": "Teste",
        "replacements": [],
        "rule": {"id": "TEST", "category": {"id": "STYLE"}},
    }]})

    with pytest.raises(LanguageToolUnavailable):
        cliente(session).check("A😀B", "pt")


@pytest.mark.parametrize("payload", [
    None,
    {},
    {"matches": None},
    {"matches": [{}]},
    {"matches": [{"offset": True, "length": 1, "message": "x", "replacements": [], "rule": {"id": "X", "category": {"id": "Y"}}}]},
])
def test_json_invalido_nunca_e_aprovado_mesmo_no_modo_opcional(session, payload):
    resposta_check(session, payload)
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


def test_json_ilegivel_nunca_e_aprovado_mesmo_no_modo_opcional(session):
    resposta_check(session, ValueError("JSON inválido"))
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


def test_redirecionamento_nao_e_tratado_como_resultado_valido(session):
    resposta_check(session, {"matches": []}, 302)
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


@pytest.mark.parametrize("failure", [OSError("connection refused"), FakeResponse({}, 503)])
def test_indisponibilidade_obrigatoria_nao_aprova(session, failure):
    if isinstance(failure, Exception):
        session.post.side_effect = [FakeResponse({"software": {"version": "6.6"}, "matches": []}), failure]
    else:
        resposta_check(session, {}, failure.status_code)
    with pytest.raises(LanguageToolUnavailable):
        cliente(session).check("Texto", "pt")


def test_indisponibilidade_opcional_retorna_sem_achados(session):
    session.post.side_effect = [
        FakeResponse({"software": {"version": "6.6"}, "matches": []}),
        OSError("connection refused"),
    ]
    assert cliente(session, required=False).check("Texto", "pt") == ()


def test_check_verifica_health_uma_vez_por_instancia(session):
    client = cliente(session)

    assert client.check("Primeiro", "pt") == ()
    assert client.check("Segundo", "en") == ()
    assert session.get.call_count == 1
    assert session.post.call_count == 3


def test_health_verifica_versao_e_locales_com_respostas_standalone(session):
    session.get.return_value = FakeResponse([
        {"name": "Portuguese (Brazil)", "code": "pt", "longCode": "pt-BR"},
        {"name": "English (US)", "code": "en", "longCode": "en-US"},
        {"name": "Spanish", "code": "es", "longCode": "es"},
    ])
    session.post.return_value = FakeResponse({
        "software": {"name": "LanguageTool", "version": "6.6", "buildDate": "2024-03-28", "apiVersion": 1},
        "language": {"name": "English (US)", "code": "en-US"},
        "matches": [],
    })

    report = cliente(session, url="http://localhost:8081/v2").health()
    assert report.version == "6.6"
    assert set(report.locales) == {"pt-BR", "en-US", "es"}
    session.get.assert_called_once()
    args, kwargs = session.get.call_args
    assert args == ("http://localhost:8081/v2/languages",)
    assert kwargs["timeout"] == 15.0
    assert kwargs["allow_redirects"] is False
    assert select_proxy(args[0], kwargs["proxies"]) is None
    assert session.post.call_args.args == ("http://localhost:8081/v2/check",)


@pytest.mark.parametrize("version,locales", [
    ("6.5", ["pt-BR", "en-US", "es"]),
    ("6.6", ["pt-BR", "en-US"]),
])
def test_health_recusa_versao_ou_locale_ausente(session, version, locales):
    session.get.return_value = FakeResponse([
        {"name": code, "code": code.split("-")[0], "longCode": code}
        for code in locales
    ])
    session.post.return_value = FakeResponse({"software": {"name": "LanguageTool", "version": version}, "matches": []})
    with pytest.raises(LanguageToolUnavailable):
        cliente(session).health(expected_version="6.6")


def test_health_recusa_json_invalido(session):
    session.get.return_value = FakeResponse({"languages": []})
    session.post.return_value = FakeResponse({"software": {"version": "6.6"}, "matches": []})
    with pytest.raises(LanguageToolUnavailable):
        cliente(session).health()
