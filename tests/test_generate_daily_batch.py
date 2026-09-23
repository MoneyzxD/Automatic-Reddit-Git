from scripts import generate_daily_batch


def test_preenche_tres_videos_com_historia_de_duas_e_uma_parte(monkeypatch):
    contagens = {"pt": 0, "en": 0, "es": 0}
    chamadas = []

    monkeypatch.setattr(
        generate_daily_batch,
        "_contar_lote_do_dia",
        lambda idiomas: {idioma: contagens[idioma] for idioma in idiomas},
    )

    def executar(idiomas, max_parts, dry_run=False, test_story=False):
        chamadas.append((idiomas, max_parts))
        partes = 2 if len(chamadas) == 1 else 1
        for idioma in idiomas:
            contagens[idioma] += partes
        return 0

    monkeypatch.setattr(generate_daily_batch, "_executar_historia", executar)

    resultado = generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 6)

    assert resultado == {"pt": 3, "en": 3, "es": 3}
    assert chamadas == [(["pt", "en", "es"], 3), (["pt", "en", "es"], 1)]


def test_falha_sem_ultrapassar_meta_quando_nao_encontra_historia(monkeypatch):
    monkeypatch.setattr(
        generate_daily_batch,
        "_contar_lote_do_dia",
        lambda idiomas: {idioma: 2 for idioma in idiomas},
    )
    monkeypatch.setattr(
        generate_daily_batch,
        "_executar_historia",
        lambda idiomas, max_parts, dry_run=False, test_story=False: 0,
    )

    try:
        generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 2)
    except RuntimeError as erro:
        assert "Nao foi possivel completar" in str(erro)
    else:
        raise AssertionError("Deveria falhar quando o lote nao progride")


def test_meta_maior_que_tres_mantem_limite_por_historia(monkeypatch):
    contagens = {"pt": 0}
    limites = []

    monkeypatch.setattr(
        generate_daily_batch,
        "_contar_lote_do_dia",
        lambda idiomas: {idioma: contagens[idioma] for idioma in idiomas},
    )

    def executar(idiomas, max_parts, dry_run=False, test_story=False):
        limites.append(max_parts)
        contagens["pt"] += max_parts
        return 0

    monkeypatch.setattr(generate_daily_batch, "_executar_historia", executar)

    resultado = generate_daily_batch.preencher_lote(["pt"], 5, 8)

    assert resultado == {"pt": 5}
    assert limites == [3, 2]
