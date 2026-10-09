"""Executa a preparação real do workflow sem sudo, APT ou rede reais."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


BASE_DIR = Path(__file__).resolve().parents[1]


def _step():
    workflow = yaml.load(
        (BASE_DIR / ".github/workflows/pipeline.yml").read_text(encoding="utf-8"),
        Loader=yaml.BaseLoader,
    )
    return next(s for s in workflow["jobs"]["gerar-e-publicar"]["steps"]
                if s.get("name") == "Instalar FFmpeg")


# Só o shell/controlador é real: operações administrativas são substituídas.
STUBS = r'''
timeout() {
  [[ "$1" == --kill-after=*s ]] || return 90
  shift
  bound="${1%s}"
  [[ "$bound" =~ ^[0-9]+$ && "$bound" -gt 0 && "$bound" -le 300 ]] || return 91
  shift
  printf 'BOUND %s %s\n' "$bound" "$*" >&2
  if [[ "${FAIL_PHASE:-}" == update && "$*" == *apt-get*update* ]] ||
     [[ "${FAIL_PHASE:-}" == install && "$*" == *apt-get*install* ]]; then
    return 124
  fi
  "$@"
}
sudo() {
  [[ "$1" == -n ]] || return 92
  shift
  if [[ "$1" == env ]]; then
    shift
    [[ "$1" == DEBIAN_FRONTEND=noninteractive ]] || return 93
    shift
  fi
  "$@"
}
systemctl() {
  [[ "$1" == stop ]] || return 94
  printf 'TIMER_STOP\n'
  [[ "${FAIL_PHASE:-}" != timer ]]
}
rm() {
  [[ "$*" == '-f /etc/apt/sources.list.d/google-chrome.list' ]] || return 95
  printf 'CHROME_SOURCE\n'
}
apt-get() {
  printf 'APT %s\n' "$*"
  [[ "$*" == *'DPkg::Lock::Timeout=60'* ]] || return 96
  [[ "$*" == *'Acquire::http::Timeout=30'* ]] || return 97
  [[ "$*" == *'Acquire::https::Timeout=30'* ]] || return 98
}
ffmpeg() {
  printf 'FFMPEG_VERSION\n'
  [[ "${FAIL_PHASE:-}" != ffmpeg ]]
}
fc-list() {
  [[ "${FAIL_PHASE:-}" != fonts ]] || return 0
  printf '/font/DejaVuSans-Bold.ttf: DejaVu Sans\n'
}
fuser() { return 99; }
'''


def _run(tmp_path, failure=""):
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    return subprocess.run(
        [bash, "-e", "-o", "pipefail", "-c", STUBS + _step()["run"]],
        cwd=tmp_path, env=dict(os.environ, FAIL_PHASE=failure),
        capture_output=True, text=True, timeout=10,
    )


def test_setup_instala_as_duas_dependencias_com_esperas_limitadas(tmp_path):
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    apt_lines = [line for line in result.stdout.splitlines() if line.startswith("APT ")]
    assert len(apt_lines) == 2
    assert "update" in apt_lines[0]
    assert "install" in apt_lines[1]
    assert "ffmpeg" in apt_lines[1] and "fonts-dejavu-core" in apt_lines[1]
    assert result.stdout.index("CHROME_SOURCE") < result.stdout.index("APT ")
    assert "FFMPEG_VERSION" in result.stdout


@pytest.mark.parametrize("phase", ["update", "install", "ffmpeg", "fonts"])
def test_falha_de_preparacao_identifica_fase_e_nao_continua(tmp_path, phase):
    result = _run(tmp_path, phase)
    assert result.returncode != 0
    assert f"fase={phase}" in result.stderr
    if phase in ("update", "install"):
        assert "codigo=124" in result.stderr
        assert "FFMPEG_VERSION" not in result.stdout
    if phase == "update":
        assert not any("install" in line for line in result.stdout.splitlines()
                       if line.startswith("APT "))


def test_timer_indisponivel_nao_esconde_erro_de_apt(tmp_path):
    result = _run(tmp_path, "timer")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "AVISO" in result.stdout + result.stderr
    assert "FFMPEG_VERSION" in result.stdout


def test_workflow_limita_preparacao_sem_ignorar_falha_do_step():
    step = _step()
    assert 1 <= int(step.get("timeout-minutes", "0")) <= 10
    assert step.get("continue-on-error", "false") == "false"
