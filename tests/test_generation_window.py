"""Prazo real informado pelo Gemini, sem chamar a API nem alterar filas."""
from datetime import datetime, timezone
import pytest

from utils.generation_window import generation_allowed, main


@pytest.mark.parametrize("value,now,allowed", [
    ("", "2026-10-17T01:00:00+00:00", True),
    ("2026-10-18T00:00:05Z", "2026-10-17T09:00:00+00:00", False),
    ("2026-10-18T00:00:05Z", "2026-10-18T00:00:05+00:00", True),
    ("2026-10-17T21:00:05-03:00", "2026-10-17T23:59:59+00:00", False),
    ("2026-10-17T21:00:05-03:00", "2026-10-18T00:00:06+00:00", True),
])
def test_prazo_normaliza_fuso_e_libera_somente_apos_instante(value, now, allowed):
    assert generation_allowed(value, now=datetime.fromisoformat(now)) is allowed


@pytest.mark.parametrize("value", ["ontem", "2026-10-18", "2026-10-18T00:00:05", "2026-99-99T00:00:05Z"])
def test_prazo_invalido_nao_libera_chamada(value):
    with pytest.raises(ValueError):
        generation_allowed(value, now=datetime(2026, 10, 17, tzinfo=timezone.utc))


def test_cli_emite_bloqueio_sem_segredos_ou_chamadas_externas(monkeypatch, tmp_path, capsys):
    path = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    monkeypatch.setenv("GEMINI_RETRY_NOT_BEFORE", "2099-01-01T00:00:00Z")
    assert main() == 0
    assert path.read_text(encoding="utf-8").strip() == "allowed=false"
    assert "2099-01-01T00:00:00Z" in capsys.readouterr().out


def test_cli_prazo_malformado_falha_sem_emitir_permissao(monkeypatch, tmp_path):
    path = tmp_path / "outputs"
    monkeypatch.setenv("GITHUB_OUTPUT", str(path))
    monkeypatch.setenv("GEMINI_RETRY_NOT_BEFORE", "invalido")
    assert main() == 2 and not path.exists()
