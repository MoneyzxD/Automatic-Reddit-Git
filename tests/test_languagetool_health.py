import json
from pathlib import Path
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import parse_qs
from urllib.error import URLError

import pytest

from scripts.check_languagetool import HealthCheckFailed, wait_until_ready


BASE_DIR = Path(__file__).resolve().parent.parent
LOCALES = ("pt-BR", "en-US", "es")


@pytest.fixture
def servidor():
    state = {"version": "6.6", "locales": list(LOCALES), "checks": [], "gets": 0}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def responder(self, payload):
            status = state["statuses"].pop(0) if state.get("statuses") else state.get("status", 200)
            self.send_response(status)
            if status == 302:
                self.send_header("Location", state["redirect"])
            self.end_headers()
            self.wfile.write(b"{invalido" if state.get("invalid") else json.dumps(payload).encode())

        def do_GET(self):
            state["gets"] += 1
            assert self.path == "/v2/languages"
            self.responder([{"code": locale[:2], "longCode": locale, "name": locale} for locale in state["locales"]])

        def do_POST(self):
            assert self.path == "/v2/check"
            data = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
            state["checks"].append(data)
            self.responder(state.get("check_payload", {"software": {"name": "LanguageTool", "version": state["version"], "apiVersion": 1}, "matches": []}))

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()
    thread.join()


@pytest.mark.parametrize("suffix", ["", "/", "/v2", "/v2/", "/v2/check"])
def test_saude_normaliza_endpoint_e_aquece_tres_idiomas(servidor, suffix):
    url, state = servidor
    report = wait_until_ready(url + suffix, "6.6", LOCALES, 2)
    assert report.version == "6.6"
    assert report.locales == LOCALES
    assert [check["language"] for check in state["checks"]] == [["pt-BR"], ["en-US"], ["es"]]
    assert all(len(check["text"][0].split()) >= 3 for check in state["checks"])


@pytest.mark.parametrize("bad", [{"version": "6.5"}, {"locales": ["en-US", "es"]}, {"invalid": True}, {"status": 400}])
def test_resposta_invalida_falha_sem_retry(servidor, bad):
    url, state = servidor
    state.update(bad)
    with pytest.raises(HealthCheckFailed):
        wait_until_ready(url, "6.6", LOCALES, 1)
    assert state["gets"] == 1


@pytest.mark.parametrize("payload", [[], {"software": {"version": "6.6"}}, {"software": None, "matches": []}, {"software": {"version": 6.6}, "matches": []}])
def test_check_malformado_falha_sem_repetir_aquecimento(servidor, payload):
    url, state = servidor
    state["check_payload"] = payload
    with pytest.raises(HealthCheckFailed):
        wait_until_ready(url, "6.6", LOCALES, 1)
    assert len(state["checks"]) == 1
    assert state["gets"] == 1


def test_recusa_redirecionamento_sem_encaminhar_texto(servidor):
    url, state = servidor
    state.update(status=302, redirect=url + "/v2/check")
    with pytest.raises(HealthCheckFailed):
        wait_until_ready(url, "6.6", LOCALES, 1)
    assert state["gets"] == 1
    assert state["checks"] == []


def test_proxy_do_ambiente_nao_recebe_requisicao(servidor, monkeypatch):
    url, _ = servidor
    for key in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
        monkeypatch.setenv(key, "http://127.0.0.1:1")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")
    assert wait_until_ready(url, "6.6", LOCALES, 2).version == "6.6"


class TransientRequester:
    def __init__(self, failures):
        self.failures = failures
        self.calls = 0

    def get_json(self, url, timeout):
        self.calls += 1
        if self.calls <= self.failures:
            raise URLError(ConnectionRefusedError())
        return [{"longCode": locale} for locale in LOCALES]

    def post_form_json(self, url, data, timeout):
        return {"software": {"version": "6.6"}, "matches": []}


def test_conexao_transitoria_retorna_relatorio_apos_recuperar():
    assert wait_until_ready("http://127.0.0.1:8081", "6.6", LOCALES, 2, requester=TransientRequester(1)).version == "6.6"


def test_http_transitorio_recupera_no_mesmo_prazo(servidor):
    url, state = servidor
    state["statuses"] = [503]
    assert wait_until_ready(url, "6.6", LOCALES, 2).version == "6.6"
    assert state["gets"] == 2


def test_conexao_indisponivel_respeita_deadline():
    with pytest.raises(HealthCheckFailed, match="prazo"):
        wait_until_ready("http://127.0.0.1:8081", "6.6", LOCALES, 0.05, requester=TransientRequester(100))


@pytest.mark.parametrize("url", ["https://127.0.0.1:8081", "http://example.com:8081", "http://user:senha@localhost:8081/v2", "http://localhost:8081/v2?token=valor", "http://localhost:8081/outro", "http://localhost:0/v2"])
def test_recusa_url_insegura_antes_da_rede(url):
    with pytest.raises(HealthCheckFailed, match="URL"):
        wait_until_ready(url, "6.6", LOCALES, 1)


def test_cli_funciona_sem_site_packages_e_retorna_codigos(servidor):
    url, _ = servidor
    command = [sys.executable, "-X", "utf8", "-S", str(BASE_DIR / "scripts/check_languagetool.py"), "--url", url, "--expected-version", "6.6", "--required-locales", *LOCALES, "--timeout-seconds", "2"]
    success = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert success.returncode == 0, success.stderr
    assert "6.6" in success.stdout
    command[command.index(url)] = "http://example.com/v2"
    failure = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    assert failure.returncode == 1
    assert "URL" in failure.stderr
