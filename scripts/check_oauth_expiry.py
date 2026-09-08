#!/usr/bin/env python3
"""
scripts/check_token_expiry.py
==============================
Avisa no Telegram quando um token OAuth do YouTube esta perto de expirar.

Por que existe:
    Enquanto o app OAuth estiver em modo "Testing" no Google Cloud, cada
    token expira sozinho 7 dias apos ser gerado — sem aviso da API, sem
    forma de renovar automaticamente (exige login interativo no navegador,
    que nao existe no runner). Sem isso, a falha so aparece quando o
    upload ja da invalid_grant, no meio de uma publicacao.

Le data/oauth_token_status.json (gravado por reautenticar_youtube.py a
cada `--lang X` bem-sucedido) e manda um aviso por idioma que estiver a
2 dias ou menos do limite de 7. Roda toda vez que publish.py roda — pode
avisar mais de uma vez dentro da janela de risco (nao guarda dedupe),
o que aqui e desejavel: e melhor lembrar de novo do que esquecer.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
STATUS_FILE = BASE_DIR / "data" / "oauth_token_status.json"

LIMITE_DIAS               = 7
AVISAR_COM_DIAS_RESTANTES = 2  # avisa quando faltar <= 2 dias pro limite


def check_and_warn() -> None:
    if not STATUS_FILE.exists():
        return

    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    agora = datetime.now(timezone.utc)

    for lang, gerado_em_str in status.items():
        try:
            gerado_em = datetime.fromisoformat(gerado_em_str)
        except ValueError:
            continue

        dias_passados  = (agora - gerado_em).total_seconds() / 86400
        dias_restantes = LIMITE_DIAS - dias_passados

        if dias_restantes > AVISAR_COM_DIAS_RESTANTES:
            continue

        from scheduler.notifier import send_admin_alert

        if dias_restantes <= 0:
            msg = (
                f"Token OAuth do YouTube ({lang.upper()}) provavelmente ja "
                f"expirou (gerado ha {dias_passados:.1f} dias, limite e "
                f"{LIMITE_DIAS}). Renove: "
                f"python scripts/reautenticar_youtube.py --lang {lang}"
            )
        else:
            msg = (
                f"Token OAuth do YouTube ({lang.upper()}) expira em "
                f"~{dias_restantes:.1f} dia(s). Renove com antecedencia: "
                f"python scripts/reautenticar_youtube.py --lang {lang}"
            )
        send_admin_alert(msg)


if __name__ == "__main__":
    check_and_warn()
