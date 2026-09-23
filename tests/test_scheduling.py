from datetime import datetime, timezone

from scheduler import scheduling


CANAL_UTC = {
    "timezone": "UTC",
    "posting_windows_by_weekday": {
        dia: {"start": "10:00", "end": "22:00"}
        for dia in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    },
}


def test_quarta_parte_fica_no_dia_seguinte(monkeypatch):
    monkeypatch.setattr(scheduling.random, "randint", lambda inicio, fim: 0)
    agora = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)

    horarios = scheduling.next_publish_slots(
        "pt",
        CANAL_UTC,
        4,
        intervalo_minutos=90,
        agora=agora,
        limite_por_dia=3,
    )

    assert [horario.date().isoformat() for horario in horarios] == [
        "2030-01-01",
        "2030-01-01",
        "2030-01-01",
        "2030-01-02",
    ]


def test_parte_herdada_ocupa_uma_vaga_do_dia(monkeypatch):
    monkeypatch.setattr(scheduling.random, "randint", lambda inicio, fim: 0)
    agora = datetime(2030, 1, 2, 9, 0, tzinfo=timezone.utc)

    horarios = scheduling.next_publish_slots(
        "pt",
        CANAL_UTC,
        3,
        intervalo_minutos=90,
        agora=agora,
        limite_por_dia=3,
        ocupacao_por_dia={"2030-01-02": 1},
    )

    assert [horario.date().isoformat() for horario in horarios] == [
        "2030-01-02",
        "2030-01-02",
        "2030-01-03",
    ]
