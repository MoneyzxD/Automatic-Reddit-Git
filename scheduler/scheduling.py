"""
scheduler/scheduling.py
=======================
Calcula QUANDO um video deve ser publicado — nao quando o job roda.

Por que isso existe (peca central da migracao):
    Ate aqui, "postar no horario certo" dependia de um processo vivo
    (APScheduler) que checava a cada 5 min "estou dentro da janela agora?".
    Em runner efemero do GitHub Actions isso nao existe: o job roda quando o
    cron dispara — com atraso de 10-30 min em horario de pico — e morre.

    A solucao e desacoplar as duas coisas:
        - o job SOBE o video quando rodar (a hora que for)
        - o YouTube SEGURA o video privado e publica sozinho no publishAt

    Assim o atraso do cron vira irrelevante: o horario de publicacao passa a
    ser um dado enviado na API, nao o instante em que o upload aconteceu.

    O mesmo calculo serve numa VM (Oracle/VPS) sem nenhuma alteracao — e so
    outra forma de decidir o publishAt.

Regras respeitadas (todas ja existentes em publishing.yaml):
    - janela de postagem por dia da semana, no fuso do canal
    - intervalo minimo entre publicacoes do mesmo idioma
    - jitter aleatorio para nao publicar sempre no mesmo minuto exato
    - nunca agenda no passado (a API do YouTube rejeita)
"""
from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_DIAS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

#: Antecedencia minima entre o upload e a publicacao. A API do YouTube exige
#: publishAt no futuro; esta folga tambem cobre o tempo do proprio upload.
LEAD_MINIMO_MINUTOS = 15

#: Jitter aplicado ao horario final para nao publicar sempre no mesmo minuto.
JITTER_MAXIMO_MINUTOS = 20

#: Janela padrao quando o idioma nao tem configuracao para aquele dia.
JANELA_PADRAO = {"start": "10:00", "end": "22:00"}


def _fuso(channel_cfg: dict):
    """Fuso do canal, com UTC como fallback seguro."""
    nome = channel_cfg.get("timezone", "UTC")
    try:
        import pytz
        return pytz.timezone(nome)
    except Exception as e:
        logger.warning("Fuso '%s' invalido (%s) — usando UTC", nome, e)
        import pytz
        return pytz.UTC


def _janela_do_dia(channel_cfg: dict, dia_semana: int) -> tuple[str, str]:
    janelas = channel_cfg.get("posting_windows_by_weekday", {}) or {}
    janela = janelas.get(_DIAS[dia_semana]) or JANELA_PADRAO
    return janela.get("start", "10:00"), janela.get("end", "22:00")


def _hora_para_datetime(base: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return base.replace(hour=h, minute=m, second=0, microsecond=0)


def _primeira_janela_apos(channel_cfg: dict, alvo: datetime) -> datetime:
    """
    Primeiro instante >= `alvo` que cai dentro de uma janela de postagem.
    Procura no dia do alvo e ate 7 dias adiante.
    """
    for offset in range(0, 8):
        dia = (alvo + timedelta(days=offset)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        inicio_txt, fim_txt = _janela_do_dia(channel_cfg, dia.weekday())
        inicio = _hora_para_datetime(dia, inicio_txt)
        fim    = _hora_para_datetime(dia, fim_txt)

        # Janela que cruza a meia-noite (ex: 22:00 -> 02:00)
        if fim <= inicio:
            fim += timedelta(days=1)

        candidato = max(inicio, alvo)   # alvo e absoluto, vale em qualquer dia
        if candidato <= fim:
            jitter = timedelta(minutes=random.randint(0, JITTER_MAXIMO_MINUTOS))
            return min(candidato + jitter, fim)

    return alvo + timedelta(hours=1)


def next_publish_slots(
    language: str,
    channel_cfg: dict,
    quantidade: int,
    intervalo_minutos: int | None = None,
    agora: datetime | None = None,
) -> list[datetime]:
    """
    Calcula `quantidade` horarios de publicacao, em UTC, em ordem crescente.

    Calculo SEQUENCIAL com cursor: cada horario e ancorado no anterior, nao
    em "agora + N * intervalo". A diferenca importa quando a fila transborda
    para o dia seguinte — com ancoragem absoluta, todos os itens excedentes
    colapsavam no inicio da janela seguinte e saiam fora de ordem (bug real
    observado: o 3o video era agendado antes do 2o).

    intervalo_minutos: espacamento entre publicacoes. Se None, usa
        min_interval_minutes do canal (que o growth_plan ajusta por idade da
        conta).
    """
    if quantidade <= 0:
        return []

    tz = _fuso(channel_cfg)
    agora_local = (agora or datetime.now(timezone.utc)).astimezone(tz)

    if intervalo_minutos is None:
        intervalo_minutos = int(channel_cfg.get("min_interval_minutes", 360))

    cursor = agora_local + timedelta(minutes=LEAD_MINIMO_MINUTOS)
    horarios: list[datetime] = []

    for _ in range(quantidade):
        slot = _primeira_janela_apos(channel_cfg, cursor)
        # Garantia dura: a API do YouTube rejeita publishAt no passado
        if slot <= agora_local:
            slot = agora_local + timedelta(minutes=LEAD_MINIMO_MINUTOS)
        horarios.append(slot.astimezone(timezone.utc))
        cursor = slot + timedelta(minutes=intervalo_minutos)

    logger.info(
        "Agendamento (%s): %d publicacao(oes), de %s a %s UTC",
        language, len(horarios),
        horarios[0].strftime("%d/%m %H:%M"),
        horarios[-1].strftime("%d/%m %H:%M"),
    )
    return horarios


def next_publish_slot(
    language: str,
    channel_cfg: dict,
    ja_agendados: int = 0,
    intervalo_minutos: int | None = None,
    agora: datetime | None = None,
) -> datetime:
    """
    Conveniencia para um unico horario. Para varios videos prefira
    next_publish_slots(), que garante ordem crescente entre eles.
    """
    horarios = next_publish_slots(
        language, channel_cfg, ja_agendados + 1, intervalo_minutos, agora
    )
    return horarios[-1]


def to_youtube_timestamp(dt: datetime) -> str:
    """
    Formata para o publishAt da API do YouTube (ISO 8601 em UTC, com Z).
    Ex: 2026-08-18T14:30:00Z
    """
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
