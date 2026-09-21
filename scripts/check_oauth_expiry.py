#!/usr/bin/env python3
"""
scripts/check_oauth_expiry.py
==============================
Avisa no Telegram quando uma credencial perto de expirar: token OAuth do
YouTube ou cookie de sessao do Reddit.

Por que existe:
    Enquanto o app OAuth estiver em modo "Testing" no Google Cloud, cada
    token do YouTube expira sozinho 7 dias apos ser gerado — sem aviso da
    API, sem forma de renovar automaticamente (exige login interativo no
    navegador, que nao existe no runner). O cookie de sessao do Reddit dura
    bem mais (~6 meses), mas tambem exige DevTools manual pra renovar — sem
    aviso, a falha so aparece quando a extracao/upload ja quebrou.

Roda toda vez que publish.py roda — pode avisar mais de uma vez dentro da
janela de risco (nao guarda dedupe), o que aqui e desejavel: e melhor
lembrar de novo do que esquecer.
"""
from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR    = Path(__file__).parent.parent
STATUS_FILE = BASE_DIR / "data" / "oauth_token_status.json"

LIMITE_DIAS_YOUTUBE               = 7
AVISAR_YOUTUBE_COM_DIAS_RESTANTES = 2

AVISAR_REDDIT_COM_DIAS_RESTANTES = 14  # cookie dura ~6 meses, folga maior


def youtube_oauth_em_teste() -> bool:
    """Indica se ainda se aplica o vencimento de sete dias do Google."""
    status = os.environ.get("YOUTUBE_OAUTH_PUBLISHING_STATUS", "testing")
    return status.strip().lower() != "production"


def _decodificar_exp_jwt(jwt: str) -> datetime | None:
    """Le so o campo 'exp' do payload de um JWT, sem verificar assinatura
    (nao precisamos validar — so queremos saber quando expira)."""
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * (-len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    except Exception:
        return None


def _checar_youtube(agora: datetime) -> None:
    if not youtube_oauth_em_teste():
        return
    if not STATUS_FILE.exists():
        return
    try:
        status = json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    for lang, gerado_em_str in status.items():
        try:
            gerado_em = datetime.fromisoformat(gerado_em_str)
        except ValueError:
            continue

        dias_passados  = (agora - gerado_em).total_seconds() / 86400
        dias_restantes = LIMITE_DIAS_YOUTUBE - dias_passados
        if dias_restantes > AVISAR_YOUTUBE_COM_DIAS_RESTANTES:
            continue

        from scheduler.notifier import send_admin_alert

        if dias_restantes <= 0:
            msg = (
                f"Token OAuth do YouTube ({lang.upper()}) provavelmente ja "
                f"expirou (gerado ha {dias_passados:.1f} dias, limite e "
                f"{LIMITE_DIAS_YOUTUBE}). Renove: "
                f"python scripts/reautenticar_youtube.py --lang {lang}"
            )
        else:
            msg = (
                f"Token OAuth do YouTube ({lang.upper()}) expira em "
                f"~{dias_restantes:.1f} dia(s). Renove com antecedencia: "
                f"python scripts/reautenticar_youtube.py --lang {lang}"
            )
        send_admin_alert(msg)


def _checar_reddit(agora: datetime) -> None:
    from utils import environment as env

    cookie = env.reddit_session_cookie()
    if not cookie:
        return

    m = re.search(r"reddit_session=([^;]+)", cookie)
    if not m:
        return

    expira_em = _decodificar_exp_jwt(m.group(1))
    if expira_em is None:
        return

    dias_restantes = (expira_em - agora).total_seconds() / 86400
    if dias_restantes > AVISAR_REDDIT_COM_DIAS_RESTANTES:
        return

    from scheduler.notifier import send_admin_alert

    if dias_restantes <= 0:
        msg = (
            "Cookie de sessao do Reddit provavelmente ja expirou. "
            "Refaça o login no reddit.com e pegue o cabecalho Cookie de novo "
            "(DevTools > Network > qualquer requisicao > Request Headers)."
        )
    else:
        msg = (
            f"Cookie de sessao do Reddit expira em ~{dias_restantes:.0f} "
            "dia(s). Renove com antecedencia: refaça o login no reddit.com "
            "e pegue o cabecalho Cookie de novo (DevTools > Network)."
        )
    send_admin_alert(msg)


def check_and_warn() -> None:
    agora = datetime.now(timezone.utc)
    _checar_youtube(agora)
    _checar_reddit(agora)


if __name__ == "__main__":
    check_and_warn()
