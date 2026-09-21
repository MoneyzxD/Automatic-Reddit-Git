from scripts.check_oauth_expiry import youtube_oauth_em_teste


def test_oauth_testing_mantem_alerta_de_sete_dias(monkeypatch):
    monkeypatch.delenv("YOUTUBE_OAUTH_PUBLISHING_STATUS", raising=False)

    assert youtube_oauth_em_teste() is True


def test_oauth_production_desativa_alerta_de_sete_dias(monkeypatch):
    monkeypatch.setenv("YOUTUBE_OAUTH_PUBLISHING_STATUS", "production")

    assert youtube_oauth_em_teste() is False
