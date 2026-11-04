"""Seleção explícita e canal confirmado antes de sobrescrever credenciais."""
import sys
from types import SimpleNamespace

import pytest


@pytest.mark.parametrize("correct", [True, False])
def test_escolhe_conta_e_preserva_token_se_canal_errado(tmp_path, monkeypatch, correct):
    from scripts import reautenticar_youtube as auth
    credentials = tmp_path / "client.json"
    credentials.write_text("{}")
    token = tmp_path / "secrets/youtube_token_pt.json"
    token.parent.mkdir()
    token.write_text("anterior")
    status = tmp_path / "status.json"
    status.write_text("{}")
    monkeypatch.setattr(auth, "BASE_DIR", tmp_path)
    monkeypatch.setattr(auth, "STATUS_FILE", status)
    monkeypatch.setattr("builtins.input", lambda _: "s")
    monkeypatch.setattr(sys, "argv", ["auth", "--lang", "pt", "--credentials", str(credentials),
                                    "--login-hint", "owner@example.com"])
    calls = []
    def server(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(to_json=lambda: "novo")
    flow = SimpleNamespace(run_local_server=server)
    monkeypatch.setattr("google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file", lambda *a: flow)
    owner = {"id": "UC3p2paTQWBFzhvcJ-vobcJQ" if correct else "outro", "snippet": {"title": "Canal"}}
    service = SimpleNamespace(channels=lambda: SimpleNamespace(list=lambda **k: SimpleNamespace(
        execute=lambda: {"items": [owner]})))
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **k: service)
    assert auth.main() == (0 if correct else 1)
    assert calls[0]["prompt"] == "select_account consent"
    assert calls[0]["login_hint"] == "owner@example.com"
    assert token.read_text() == ("novo" if correct else "anterior")
    assert (status.read_text() != "{}") is correct
