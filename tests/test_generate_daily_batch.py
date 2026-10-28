import os
import subprocess
import sys
import pytest
from pathlib import Path

from scripts import generate_daily_batch


def test_meta_um_pula_recusa_de_conteudo_e_exige_video_sem_reabrir_fonte(monkeypatch):
    count, calls = 0, []
    monkeypatch.setattr(generate_daily_batch, "_contar_lote_do_dia", lambda langs: {"pt": count})
    def story(languages, max_parts):
        nonlocal count
        calls.append((languages, max_parts))
        if len(calls) == 2:
            count = 1
        return 0
    monkeypatch.setattr(generate_daily_batch, "_executar_historia", story)
    assert generate_daily_batch.preencher_lote(["pt"], 1, 6) == {"pt": 1}
    assert calls == [(["pt"], 2), (["pt"], 2)]


def test_indisponibilidade_do_idioma_para_sem_tentar_historia_nova(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_daily_batch, "setup_logging", lambda *args: None, raising=False)
    monkeypatch.setattr(generate_daily_batch, "_contar_lote_do_dia", lambda langs: {lang: 0 for lang in langs})
    def outage(*args, **kwargs):
        calls.append(args)
        return 4
    monkeypatch.setattr(generate_daily_batch, "_executar_historia", outage)
    assert generate_daily_batch.main(["--lang", "pt"]) == 2
    assert len(calls) == 1


def test_cota_es_nao_impede_pt_en_de_completar_meta(monkeypatch):
    counts = dict(pt=0, en=0, es=0)
    calls = []
    monkeypatch.setattr(generate_daily_batch, "_contar_lote_do_dia",
                        lambda langs: {lang: counts[lang] for lang in langs})
    def story(langs, max_parts):
        assert len(langs) == 1
        lang = langs[0]
        calls.append(lang)
        if lang == "es":
            return 4
        counts[lang] += 1
        return 0
    monkeypatch.setattr(generate_daily_batch, "_executar_historia", story)
    with pytest.raises(generate_daily_batch.BatchUnavailable, match="es"):
        generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 6)
    assert counts == dict(pt=3, en=3, es=0)
    assert calls.count("es") == 1


def test_estado_inseguro_codigo_2_continua_parando_todos_idiomas(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_daily_batch, "_contar_lote_do_dia", lambda langs: dict.fromkeys(langs, 0))
    monkeypatch.setattr(generate_daily_batch, "_executar_historia",
                        lambda langs, limit: calls.append(langs) or 2)
    with pytest.raises(generate_daily_batch.BatchUnavailable, match="codigo 2"):
        generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 6)
    assert calls == [["pt"]]


def test_script_encontra_main_quando_executado_fora_da_raiz(tmp_path):
    script = Path(generate_daily_batch.__file__).resolve()
    ambiente = os.environ.copy()
    ambiente["PYTHONPATH"] = ""

    resultado = subprocess.run(
        [sys.executable, str(script), "--dry-run"],
        cwd=tmp_path,
        env=ambiente,
        capture_output=True,
        text=True,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr


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
        partes = 2 if contagens[idiomas[0]] == 0 else 1
        for idioma in idiomas:
            contagens[idioma] += partes
        return 0

    monkeypatch.setattr(generate_daily_batch, "_executar_historia", executar)

    resultado = generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 6)

    assert resultado == {"pt": 3, "en": 3, "es": 3}
    assert chamadas == [(["pt"], 3), (["en"], 3), (["es"], 3),
                        (["pt"], 2), (["en"], 2), (["es"], 2)]


def test_uma_parte_mais_historia_de_tres_leva_uma_para_amanha(monkeypatch):
    contagens = {"pt": 0}
    chamadas = []

    monkeypatch.setattr(
        generate_daily_batch,
        "_contar_lote_do_dia",
        lambda idiomas: {idioma: contagens[idioma] for idioma in idiomas},
    )

    def executar(idiomas, max_parts, dry_run=False, test_story=False):
        chamadas.append(max_parts)
        contagens["pt"] += 1 if len(chamadas) == 1 else 3
        return 0

    monkeypatch.setattr(generate_daily_batch, "_executar_historia", executar)

    resultado = generate_daily_batch.preencher_lote(["pt"], 3, 6)

    assert resultado == {"pt": 4}
    assert chamadas == [3, 3]


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

    assert resultado == {"pt": 6}
    assert limites == [3, 3]
