from scheduler import runner


def test_meta_diaria_controla_geracao_e_limite_de_publicacao(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_TARGET", "5")
    publicacao = {
        "daily_video_plan": {
            "enabled": True,
            "target_per_language": 3,
            "maximum_target_per_language": 10,
            "interval_minutes_by_target": {5: 90, 10: 60},
        }
    }

    limites = runner._get_limits_for_channel({}, publicacao)

    assert limites == {"max_uploads_per_day": 5, "min_interval_minutes": 90}


def test_meta_diaria_nunca_ultrapassa_maximo_configurado(monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_TARGET", "50")
    publicacao = {
        "daily_video_plan": {
            "enabled": True,
            "target_per_language": 3,
            "maximum_target_per_language": 10,
            "interval_minutes_by_target": {10: 60},
        }
    }

    limites = runner._get_limits_for_channel({}, publicacao)

    assert limites == {"max_uploads_per_day": 10, "min_interval_minutes": 60}
