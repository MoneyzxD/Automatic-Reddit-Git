#!/usr/bin/env bash
# Instala o runtime local pinado; executar com sudo apenas no host Linux alvo.
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Execute o instalador como root no host Linux alvo." >&2
  exit 1
fi
repo_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo_dir/config/languagetool_runtime.env"
source /etc/os-release
python_bin=python3

# O repositório Adoptium usa codenames DEB e a versão MAIOR no RHEL/Oracle.
case "$ID:$VERSION_ID" in
  ubuntu:22.04|ubuntu:24.04|debian:12|debian:13)
    command -v apt-get >/dev/null
    apt-get update
    apt-get install -y ca-certificates curl unzip gnupg python3
    curl --fail --silent --show-error --location https://packages.adoptium.net/artifactory/api/gpg/key/public |
      gpg --dearmor --yes --output /usr/share/keyrings/adoptium.gpg
    printf 'deb [signed-by=/usr/share/keyrings/adoptium.gpg] https://packages.adoptium.net/artifactory/deb %s main\n' "$VERSION_CODENAME" > /etc/apt/sources.list.d/adoptium.list
    apt-get update
    apt-get install -y temurin-17-jdk
    java_bin=$(dpkg-query -L temurin-17-jdk | awk '/\/bin\/java$/ { print; exit }')
    ;;
  ol:8|ol:8.*|ol:9|ol:9.*|rhel:8|rhel:8.*|rhel:9|rhel:9.*)
    command -v dnf >/dev/null
    major_version=${VERSION_ID%%.*}
    if [[ $major_version == 8 ]]; then
      # Python 3.11 vem do AppStream de EL8 8.8+; python3 permanece em 3.6.
      python_bin=python3.11
    fi
    # Oracle Linux mantém compatibilidade com os pacotes oficiais RHEL.
    printf '[Adoptium]\nname=Adoptium\nbaseurl=https://packages.adoptium.net/artifactory/rpm/rhel/%s/$basearch\nenabled=1\ngpgcheck=1\ngpgkey=https://packages.adoptium.net/artifactory/api/gpg/key/public\n' "$major_version" > /etc/yum.repos.d/adoptium.repo
    dnf install -y temurin-17-jdk ca-certificates curl unzip "$python_bin" shadow-utils
    java_bin=$(rpm -ql temurin-17-jdk | awk '/\/bin\/java$/ { print; exit }')
    ;;
  *)
    echo "Distribuição não suportada: use Debian 12/13, Ubuntu 22.04/24.04 ou Oracle Linux/RHEL 8/9." >&2
    exit 1
    ;;
esac

if ! "$python_bin" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "A verificação do LanguageTool exige Python 3.9 ou superior." >&2
  exit 1
fi

java_version=$("$java_bin" -version 2>&1)
if [[ ! $java_version =~ version\ \"17\. || $java_version != *Temurin* ]]; then
  echo "O pacote instalado não forneceu Eclipse Temurin 17." >&2
  exit 1
fi
printf '%s\n' "$java_version"

install -d -m 0755 /var/cache/languagetool /opt/languagetool
archive="/var/cache/languagetool/$LANGUAGETOOL_ARCHIVE"
if [[ ! -f $archive ]]; then
  curl --fail --silent --show-error --location --retry 3 --output "$archive" "$LANGUAGETOOL_DOWNLOAD_URL"
fi
# Verificar também em cache hit; pacote adulterado nunca chega à extração.
printf '%s  %s\n' "$LANGUAGETOOL_SHA256" "$archive" | sha256sum --check --strict
unzip -o -q "$archive" -d /opt/languagetool
if ! id -u languagetool >/dev/null 2>&1; then
  useradd --system --user-group --home-dir /opt/languagetool --no-create-home --shell "$(command -v nologin)" languagetool
fi
ln -sfn "/opt/languagetool/$LANGUAGETOOL_DIRECTORY" /opt/languagetool/current
sed "s|@JAVA_BIN@|$java_bin|g" "$repo_dir/deploy/languagetool/languagetool.service" > /etc/systemd/system/languagetool.service
systemctl daemon-reload
systemctl enable languagetool.service
systemctl restart languagetool.service
"$python_bin" "$repo_dir/scripts/check_languagetool.py" \
  --url http://127.0.0.1:8081/v2/check --expected-version "$LANGUAGETOOL_VERSION" \
  --required-locales pt-BR en-US es --timeout-seconds 120
