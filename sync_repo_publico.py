#!/usr/bin/env python3
"""
sync_repo_publico.py
====================
Sincroniza o projeto local com a pasta que e enviada ao repositorio publico.

Por que existe:
    O repositorio publico foi criado com historico limpo, numa pasta separada
    (_export_repo_publico), porque o historico antigo continha uma credencial
    versionada. Enquanto as duas pastas existirem, toda alteracao feita no
    projeto precisa ser copiada para la antes do push — este script faz isso
    de forma segura e repetivel, em vez de copiar arquivo por arquivo na mao.

Seguranca (o ponto principal deste script):
    Copia SOMENTE arquivos que o git versionaria (respeitando .gitignore) E
    que passam por um bloqueio explicito de caminhos sensiveis. O bloqueio e
    proposital e redundante: .gitignore nao remove arquivos que ja estavam
    rastreados, entao confiar so nele deixaria passar secrets/ ja versionado.
    Depois da copia, o conteudo e varrido em busca de padroes de chave (Groq,
    OAuth do Google, bot do Telegram, chaves privadas) — se achar qualquer
    coisa, ABORTA sem gravar nada.

Uso:
    python sync_repo_publico.py             # sincroniza e mostra o resumo
    python sync_repo_publico.py --verificar # so audita, nao copia nada
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
DESTINO = BASE / "_export_repo_publico"

# Bloqueio explicito por caminho — redundante em relacao ao .gitignore de
# proposito (ver docstring). Qualquer caminho que contenha um destes trechos
# nunca vai para o repositorio publico.
CAMINHOS_BLOQUEADOS = (
    "secrets/", "secrets\\", "db/", "db\\", ".key", ".pem",
    "credential", "token", "documentos/", "documentos\\",
    "atalho_oracle", "ssh-key", ".env", "_export_repo_publico",
)

# Padroes de segredo procurados NO CONTEUDO dos arquivos copiados.
PADROES_SEGREDO = {
    "chave Groq":            r"gsk_[A-Za-z0-9]{20,}",
    "OAuth client Google":   r"[0-9]+-[a-z0-9]{20,}\.apps\.googleusercontent\.com",
    "client secret Google":  r"GOCSPX-[A-Za-z0-9_-]{20,}",
    "token de bot Telegram": r"\d{8,10}:[A-Za-z0-9_-]{30,40}",
    "chave privada":         r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----",
    "chave AWS":             r"AKIA[0-9A-Z]{16}",
}


def listar_arquivos_versionaveis() -> list[str]:
    """Arquivos que o git versionaria hoje (rastreados + novos nao ignorados)."""
    r = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=BASE,
    )
    return [l for l in r.stdout.splitlines() if l.strip()]


def bloqueado(caminho: str) -> bool:
    c = caminho.lower().replace("\\", "/")
    return any(b.replace("\\", "/") in c for b in CAMINHOS_BLOQUEADOS)


def varrer_segredos(raiz: Path) -> list[tuple[str, str]]:
    """Procura padroes de segredo no conteudo. Retorna lista de (tipo, arquivo)."""
    achados = []
    for p in raiz.rglob("*"):
        if not p.is_file() or ".git" in p.parts:
            continue
        try:
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for nome, padrao in PADROES_SEGREDO.items():
            if re.search(padrao, texto):
                achados.append((nome, str(p.relative_to(raiz))))
    return achados


def main() -> int:
    parser = argparse.ArgumentParser(description="Sincroniza o export do repositorio publico")
    parser.add_argument("--verificar", action="store_true",
                        help="apenas audita o destino atual, sem copiar")
    args = parser.parse_args()

    if args.verificar:
        if not DESTINO.exists():
            print("Pasta de export nao existe ainda.")
            return 1
        achados = varrer_segredos(DESTINO)
        if achados:
            print("SEGREDOS ENCONTRADOS no export:")
            for tipo, arq in achados:
                print(f"  [{tipo}] {arq}")
            return 1
        print("Auditoria OK — nenhum segredo no export.")
        return 0

    candidatos = listar_arquivos_versionaveis()
    seguros   = [c for c in candidatos if not bloqueado(c)]
    barrados  = [c for c in candidatos if bloqueado(c)]

    print(f"Arquivos versionaveis: {len(candidatos)}")
    if barrados:
        print(f"Bloqueados por seguranca: {len(barrados)}")
        for b in barrados:
            print(f"  BLOQUEADO: {b}")

    # Preserva o .git do destino (e o repositorio publico, com o remote)
    git_dir = DESTINO / ".git"
    backup_git = None
    if git_dir.exists():
        backup_git = BASE / "_git_backup_tmp"
        if backup_git.exists():
            shutil.rmtree(backup_git)
        shutil.move(str(git_dir), str(backup_git))

    if DESTINO.exists():
        shutil.rmtree(DESTINO)
    DESTINO.mkdir()

    if backup_git:
        shutil.move(str(backup_git), str(DESTINO / ".git"))

    total = 0
    for rel in seguros:
        origem = BASE / rel
        if not origem.is_file():
            continue
        alvo = DESTINO / rel
        alvo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, alvo)
        total += origem.stat().st_size

    print(f"\nCopiados: {len(seguros)} arquivos ({total/1024/1024:.2f} MB)")

    achados = varrer_segredos(DESTINO)
    if achados:
        print("\nABORTADO — segredo encontrado no conteudo apos a copia:")
        for tipo, arq in achados:
            print(f"  [{tipo}] {arq}")
        print("Nada foi enviado. Corrija antes de dar push.")
        return 1

    print("Varredura de conteudo: nenhum segredo encontrado.")
    print(f"\nPronto. Para publicar:\n"
          f"  cd \"{DESTINO}\"\n"
          f"  git add -A\n"
          f"  git commit -m \"sua mensagem\"\n"
          f"  git push")
    return 0


if __name__ == "__main__":
    sys.exit(main())
