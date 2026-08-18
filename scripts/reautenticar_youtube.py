#!/usr/bin/env python3
"""
scripts/reautenticar_youtube.py
================================
Gera um token OAuth novo para um canal do YouTube, rodando o fluxo
interativo (abre navegador) localmente.

Por que existe:
    O token gerado uma vez fica preso ao canal que estava ATIVO no
    navegador/conta Google no momento da autorizacao — nao existe parametro
    na API para escolher o canal depois. Se a conta Google gerencia mais de
    um canal (pessoal + marca), autorizar com o canal errado selecionado
    sobe todo video pro canal errado, silenciosamente (a API nao avisa).

Antes de rodar:
    1. Abra https://studio.youtube.com no navegador.
    2. No seletor de conta (canto superior direito), troque para o canal
       CORRETO (ex: "Ah Voz do Reddit") — precisa ser o canal ativo nessa
       sessao do navegador ANTES de autorizar, senao o token sai preso no
       canal errado de novo.
    3. So entao rode este script.

Uso:
    python scripts/reautenticar_youtube.py --lang pt
    python scripts/reautenticar_youtube.py --lang en --credentials secrets/youtube_credentials.json

Depois de gerar:
    O token fica em secrets/youtube_token_<lang>.json. Copie o CONTEUDO
    desse arquivo inteiro e cole no GitHub Secret YOUTUBE_TOKEN_<LANG>
    (Settings -> Secrets and variables -> Actions), substituindo o valor
    antigo.
"""
from __future__ import annotations

import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Reautentica um canal do YouTube")
    parser.add_argument("--lang", required=True, help="idioma/canal (ex: pt, en, es)")
    parser.add_argument("--credentials", default=None,
                         help="caminho do client_secret.json (default: secrets/youtube_credentials.json)")
    args = parser.parse_args()

    credentials_file = Path(args.credentials) if args.credentials else (
        BASE_DIR / "secrets" / "youtube_credentials.json"
    )
    token_file = BASE_DIR / "secrets" / f"youtube_token_{args.lang}.json"

    if not credentials_file.exists():
        print(f"Credenciais nao encontradas: {credentials_file}")
        print("Baixe o client_secret.json do Google Cloud Console primeiro.")
        return 1

    print("Confirma antes de continuar:")
    print("  1. Abriu https://studio.youtube.com no navegador?")
    print("  2. Trocou pro canal CORRETO no seletor de conta (canto superior direito)?")
    resposta = input("Confirmado? (s/n): ").strip().lower()
    if resposta != "s":
        print("Cancelado. Troque o canal ativo no navegador e rode de novo.")
        return 1

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow  = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
    creds = flow.run_local_server(port=0)

    token_file.parent.mkdir(parents=True, exist_ok=True)
    with open(token_file, "w") as f:
        f.write(creds.to_json())

    print(f"\nToken salvo em: {token_file}")
    print(f"Agora copie o CONTEUDO desse arquivo para o GitHub Secret YOUTUBE_TOKEN_{args.lang.upper()}")
    print("(Settings -> Secrets and variables -> Actions -> editar o secret existente)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
