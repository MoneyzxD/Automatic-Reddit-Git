import configparser
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys

import pytest
import yaml


BASE_DIR = Path(__file__).resolve().parent.parent
MANIFEST = {
    "LANGUAGETOOL_VERSION": "6.6",
    "LANGUAGETOOL_ARCHIVE": "LanguageTool-6.6.zip",
    "LANGUAGETOOL_DIRECTORY": "LanguageTool-6.6",
    "LANGUAGETOOL_DOWNLOAD_URL": "https://languagetool.org/download/LanguageTool-6.6.zip",
    "LANGUAGETOOL_SHA256": "53600506b399bb5ffe1e4c8dec794fd378212f14aaf38ccef9b6f89314d11631",
}


def test_manifesto_identifica_arquivo_imutavel():
    entries = dict(line.split("=", 1) for line in (BASE_DIR / "config/languagetool_runtime.env").read_text().splitlines() if line and not line.startswith("#"))
    assert entries == MANIFEST


def test_unit_restringe_runtime_a_usuario_e_rede_locais():
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(BASE_DIR / "deploy/languagetool/languagetool.service", encoding="utf-8")
    service = unit["Service"]
    for key, value in {"User": "languagetool", "Group": "languagetool", "Restart": "on-failure", "ProtectSystem": "strict", "PrivateTmp": "true", "NoNewPrivileges": "true", "IPAddressDeny": "any", "IPAddressAllow": "localhost"}.items():
        assert service[key] == value
    command = shlex.split(service["ExecStart"])
    assert command[0] == "@JAVA_BIN@"
    assert command[command.index("-jar") + 1] == "/opt/languagetool/current/languagetool-server.jar"
    assert command[command.index("--port") + 1] == "8081"
    assert "--public" not in command and "--allow-origin" not in command
    assert service["WorkingDirectory"] == "/opt/languagetool/current"
    assert unit["Install"]["WantedBy"] == "multi-user.target"


def shell_commands(text):
    commands = []
    for line in text.replace("\\\n", " ").splitlines():
        try:
            words = shlex.split(line, comments=True)
        except ValueError:
            continue
        if words:
            commands.append(words)
    return commands


def test_instalador_conecta_manifesto_sha_java_unit_e_saude():
    commands = shell_commands((BASE_DIR / "scripts/install_languagetool.sh").read_text(encoding="utf-8"))
    def index(prefix):
        return next(i for i, words in enumerate(commands) if words[:len(prefix)] == prefix)

    manifest = index(["source", "$repo_dir/config/languagetool_runtime.env"])
    checksum = next(i for i, words in enumerate(commands) if "sha256sum" in words and "--check" in words and "--strict" in words)
    extraction = index(["unzip", "-o", "-q", "$archive", "-d", "/opt/languagetool"])
    symlink = index(["ln", "-sfn", "/opt/languagetool/$LANGUAGETOOL_DIRECTORY", "/opt/languagetool/current"])
    assert manifest < checksum < extraction < symlink
    user = next(words for words in commands if words[0] == "useradd")
    assert "--system" in user and "--user-group" in user and "--no-create-home" in user
    assert user[user.index("--shell") + 1] == "$(command -v nologin)"
    assert user[-1] == "languagetool"
    assert index(["systemctl", "daemon-reload"]) < index(["systemctl", "enable", "languagetool.service"]) < index(["systemctl", "restart", "languagetool.service"]) < index(["$python_bin", "$repo_dir/scripts/check_languagetool.py"])
    assert any(words[:4] == ["apt-get", "install", "-y", "temurin-17-jdk"] for words in commands)
    assert any(words[:4] == ["dnf", "install", "-y", "temurin-17-jdk"] for words in commands)
    assert any(words[0] == "sed" and "s|@JAVA_BIN@|$java_bin|g" in words for words in commands)
    health = next(words for words in commands if words[:2] == ["$python_bin", "$repo_dir/scripts/check_languagetool.py"])
    assert health[health.index("--expected-version") + 1] == "$LANGUAGETOOL_VERSION"
    assert health[health.index("--required-locales") + 1:health.index("--timeout-seconds")] == ["pt-BR", "en-US", "es"]


@pytest.mark.parametrize("major, expected", [("8", "python3.11"), ("9", "python3")])
def test_el8_instala_e_seleciona_python_versionado(major, expected):
    installer = (BASE_DIR / "scripts/install_languagetool.sh").read_text(encoding="utf-8")
    selection = "if [[ $major_version" + installer.split("if [[ $major_version", 1)[1].split("    fi", 1)[0] + "    fi\n"
    commands = shell_commands(installer)
    packages = next(words for words in commands if words[:4] == ["dnf", "install", "-y", "temurin-17-jdk"])
    assert "$python_bin" in packages
    assert "python3" not in packages
    command = "set -euo pipefail\npython_bin=python3\nmajor_version=" + major + "\n" + selection + '\nprintf "%s" "$python_bin"'
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    result = subprocess.run([bash, "-c", command], capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout == expected


@pytest.mark.parametrize("version, expected", [((3, 6), 1), ((3, 8), 1), ((3, 9), 0), ((3, 11), 0)])
def test_python_antigo_falha_antes_de_instalar_servico(version, expected):
    installer = (BASE_DIR / "scripts/install_languagetool.sh").read_text(encoding="utf-8")
    validation = 'if ! "$python_bin" -c' + installer.split('if ! "$python_bin" -c', 1)[1].split("\nfi", 1)[0] + "\nfi\n"
    assert installer.index(validation.strip()) < installer.index('sed "s|@JAVA_BIN@|$java_bin|g"')
    # Executa a expressão Python real com versão controlada, sem root/systemd.
    function = "python_mock() { " + shlex.quote(sys.executable.replace("\\", "/")) + " -c " + shlex.quote("import sys; sys.version_info=" + repr(version) + "; ") + '"$2"; }\n'
    command = "set -euo pipefail\npython_bin=python_mock\n" + function + validation
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    result = subprocess.run([bash, "-c", command], capture_output=True, text=True)
    assert result.returncode == expected


@pytest.mark.parametrize("version, expected", [
    ('openjdk version "17.0.16"\nOpenJDK Runtime Environment Temurin-17.0.16+8', 0),
    ('openjdk version "17.0.16"\nOpenJDK Runtime Environment', 1),
    ('openjdk version "21.0.8"\nOpenJDK Runtime Environment Temurin-21.0.8+9', 1),
])
def test_verificacao_java_recusa_outra_versao_ou_distribuicao(version, expected):
    installer = (BASE_DIR / "scripts/install_languagetool.sh").read_text(encoding="utf-8")
    # Executa só o bloco puro de validação; nenhuma instalação/root/systemd.
    validation = "java_version=" + installer.split("java_version=", 1)[1].split("install -d", 1)[0]
    command = "set -euo pipefail\njava_mock() { printf '%s\\n' " + shlex.quote(version) + " >&2; }\njava_bin=java_mock\n" + validation
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    result = subprocess.run([bash, "-c", command], capture_output=True, text=True)
    assert result.returncode == expected


@pytest.mark.parametrize("cached", [False, True])
def test_workflow_nao_extrai_pacote_com_checksum_invalido(tmp_path, cached):
    workflow = yaml.safe_load((BASE_DIR / ".github/workflows/pipeline.yml").read_text(encoding="utf-8"))
    step = next(step for step in workflow["jobs"]["gerar-e-publicar"]["steps"] if step.get("id") == "languagetool_package")
    bash = shutil.which("bash") or "C:/Program Files/Git/bin/bash.exe"
    config = tmp_path / "config"
    config.mkdir()
    shutil.copyfile(BASE_DIR / "config/languagetool_runtime.env", config / "languagetool_runtime.env")
    cache = tmp_path / ".cache/languagetool"
    cache.mkdir(parents=True)
    if cached:
        (cache / "LanguageTool-6.6.zip").write_bytes(b"pacote adulterado")
    # O curl simula apenas o download; o sha256sum real deve impedir o unzip.
    commands = 'curl() { while [[ $# -gt 0 ]]; do if [[ "$1" == "--output" ]]; then printf "pacote adulterado" > "$2"; return 0; fi; shift; done; return 99; }\nunzip() { touch EXTRAIDO; }\n' + step["run"]
    env = dict(os.environ, RUNNER_TEMP=str(tmp_path / "runtime"))
    result = subprocess.run([bash, "-e", "-o", "pipefail", "-c", commands], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode != 0
    assert "FAILED" in result.stdout + result.stderr
    assert not (tmp_path / "EXTRAIDO").exists()
