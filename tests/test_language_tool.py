from unittest.mock import Mock

import pytest

from stages.language_tool import LanguageIssue, LanguageToolClient, LanguageToolUnavailable


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
    return Mock()


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


def test_check_envia_locale_url_e_timeout(session):
    session.post.return_value = FakeResponse({"matches": []})

    assert cliente(session).check("Eu estou bem.", "pt-br") == ()
    session.post.assert_called_once_with(
        "http://127.0.0.1:8081/v2/check",
        data={"text": "Eu estou bem.", "language": "pt-BR"},
        timeout=15.0,
        allow_redirects=False,
    )


def test_url_base_v2_normaliza_e_usa_locale_es(session):
    session.post.return_value = FakeResponse({"matches": []})

    assert cliente(session, url="http://localhost:8081/v2").check("Hola", "es") == ()
    assert session.post.call_args.args == ("http://localhost:8081/v2/check",)
    assert session.post.call_args.kwargs["data"]["language"] == "es"


def test_override_de_ambiente_prevalece_e_normaliza(session, monkeypatch):
    monkeypatch.setenv("LANGUAGETOOL_URL", "http://[::1]:8081/v2/")
    session.post.return_value = FakeResponse({"matches": []})

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
    session.post.return_value = FakeResponse({"matches": [{
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
    session.post.return_value = FakeResponse({"matches": [{
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
    session.post.return_value = FakeResponse({"matches": [{
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
    session.post.return_value = FakeResponse(payload)
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


def test_json_ilegivel_nunca_e_aprovado_mesmo_no_modo_opcional(session):
    session.post.return_value = FakeResponse(ValueError("JSON inválido"))
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


def test_redirecionamento_nao_e_tratado_como_resultado_valido(session):
    session.post.return_value = FakeResponse({"matches": []}, 302)
    with pytest.raises(LanguageToolUnavailable):
        cliente(session, required=False).check("Texto", "pt")


@pytest.mark.parametrize("failure", [OSError("connection refused"), FakeResponse({}, 503)])
def test_indisponibilidade_obrigatoria_nao_aprova(session, failure):
    if isinstance(failure, Exception):
        session.post.side_effect = failure
    else:
        session.post.return_value = failure
    with pytest.raises(LanguageToolUnavailable):
        cliente(session).check("Texto", "pt")


def test_indisponibilidade_opcional_retorna_sem_achados(session):
    session.post.side_effect = OSError("connection refused")
    assert cliente(session, required=False).check("Texto", "pt") == ()


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
    session.get.assert_called_once_with("http://localhost:8081/v2/languages", timeout=15.0, allow_redirects=False)
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
