import publish
from scheduler import queue


def test_publicador_agenda_um_excedente_para_o_dia_seguinte(monkeypatch):
    pendentes = [
        {"id": f"video-{indice}", "video_path": "video.mp4", "metadata": {}}
        for indice in range(4)
    ]
    monkeypatch.setattr(queue, "get_pending", lambda language: pendentes)
    monkeypatch.setattr(
        queue,
        "count_scheduled_by_local_date",
        lambda language, timezone_name: {},
    )

    janelas = {
        dia: {"start": "00:00", "end": "23:59"}
        for dia in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    config = {
        "channels": {
            "pt": {
                "enabled": True,
                "timezone": "UTC",
                "posting_windows_by_weekday": janelas,
            },
        },
        "daily_video_plan": {
            "enabled": True,
            "target_per_language": 3,
            "maximum_target_per_language": 10,
            "max_carryover_parts_next_day": 1,
            "interval_minutes_by_target": {3: 90},
        },
    }

    resumo = publish.publicar_idioma("pt", config, maximo=10, dry_run=True)

    assert len(resumo["agendamentos"]) == 4


def test_publicador_nao_cria_segundo_excedente_para_amanha(monkeypatch):
    pendentes = [
        {"id": f"video-{indice}", "video_path": "video.mp4", "metadata": {}}
        for indice in range(4)
    ]
    amanha = (
        publish.datetime.now(publish.timezone.utc).date()
        + publish.timedelta(days=1)
    ).isoformat()
    monkeypatch.setattr(queue, "get_pending", lambda language: pendentes)
    monkeypatch.setattr(
        queue,
        "count_scheduled_by_local_date",
        lambda language, timezone_name: {amanha: 1},
    )
    janelas = {
        dia: {"start": "00:00", "end": "23:59"}
        for dia in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
    }
    config = {
        "channels": {
            "pt": {
                "enabled": True,
                "timezone": "UTC",
                "posting_windows_by_weekday": janelas,
            },
        },
        "daily_video_plan": {
            "enabled": True,
            "target_per_language": 3,
            "maximum_target_per_language": 10,
            "max_carryover_parts_next_day": 1,
            "interval_minutes_by_target": {3: 90},
        },
    }

    resumo = publish.publicar_idioma("pt", config, maximo=10, dry_run=True)

    assert len(resumo["agendamentos"]) == 3
