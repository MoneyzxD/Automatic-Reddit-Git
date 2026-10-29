import publish
import pytest
from datetime import datetime, timezone, timedelta
from scheduler import queue


@pytest.fixture(autouse=True)
def isolate_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(queue, "_QUEUE_DIR_PATHS", [tmp_path / "queue"])


@pytest.mark.parametrize("future_carryover", [False, True])
def test_nova_rodada_respeita_intervalo_dos_horarios_confirmados(tmp_path, monkeypatch, future_carryover):
    from scheduler import scheduling
    now = datetime(2026, 10, 29, 12, 6, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz or timezone.utc)
    monkeypatch.setattr(publish, "datetime", Clock)
    monkeypatch.setattr(scheduling, "datetime", Clock)
    monkeypatch.setattr(scheduling.random, "randint", lambda *args: 0)
    slots = [datetime(2026, 10, 29, 16, 9, tzinfo=timezone.utc),
             datetime(2026, 10, 29, 17, 40, tzinfo=timezone.utc)]
    if future_carryover:
        slots.append(datetime(2026, 10, 30, 20, 0, tzinfo=timezone.utc))
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    for i, slot in enumerate(slots):
        item = queue.enqueue("en", video, None, {}, f"Anterior {i}", story_id=f"old{i}")
        queue.update_status("en", item, "youtube", "uploaded", video_id=f"old-video-{i}",
                            publish_at=slot.isoformat())
    queue.enqueue("en", video, None, {}, "Novo", story_id="new")
    config = {
        "channels": {"en": {"enabled": True, "timezone": "America/New_York",
            "posting_windows_by_weekday": {day: {"start": "12:00", "end": "22:00"}
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}},
        "daily_video_plan": {"enabled": True, "target_per_language": 3,
            "maximum_target_per_language": 10, "max_carryover_parts_next_day": 1,
            "interval_minutes_by_target": {3: 90}},
    }

    result = publish.publicar_idioma("en", config, maximo=3, dry_run=True)

    assert len(result["agendamentos"]) == 1
    planned = datetime.fromisoformat(result["agendamentos"][0][1].replace("Z", "+00:00"))
    assert all(abs(planned - slot) >= timedelta(minutes=90) for slot in slots)
    assert planned.date() == now.date()
    assert len(queue.get_pending("en")) == 1


def test_intervalo_no_fim_da_janela_nao_envia_mais_de_um_excedente(tmp_path, monkeypatch):
    from scheduler import scheduling
    now = datetime(2026, 10, 29, 20, 45, tzinfo=timezone.utc)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now.astimezone(tz or timezone.utc)
    monkeypatch.setattr(publish, "datetime", Clock)
    monkeypatch.setattr(scheduling, "datetime", Clock)
    monkeypatch.setattr(scheduling.random, "randint", lambda *args: 0)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    old = queue.enqueue("pt", video, None, {}, "Anterior", story_id="old")
    queue.update_status("pt", old, "youtube", "uploaded", video_id="old-video",
                        publish_at="2026-10-29T21:00:00Z")
    for i in range(3):
        queue.enqueue("pt", video, None, {}, "Novo", story_id=f"new{i}")
    config = {
        "channels": {"pt": {"enabled": True, "timezone": "UTC",
            "posting_windows_by_weekday": {day: {"start": "10:00", "end": "22:00"}
                for day in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}}},
        "daily_video_plan": {"enabled": True, "target_per_language": 3,
            "maximum_target_per_language": 10, "max_carryover_parts_next_day": 1,
            "interval_minutes_by_target": {3: 90}},
    }
    before = queue._queue_path("pt").read_bytes()

    result = publish.publicar_idioma("pt", config, maximo=3, dry_run=True)

    assert len(result["agendamentos"]) == 1
    assert result["agendamentos"][0][1] == "2026-10-30T10:00:00Z"
    assert queue._queue_path("pt").read_bytes() == before


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
