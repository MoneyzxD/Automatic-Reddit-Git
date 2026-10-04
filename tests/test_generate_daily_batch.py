import os
import subprocess
import sys
import pytest
from pathlib import Path

from scripts import generate_daily_batch


def test_indisponibilidade_codigo_2_para_lote_sem_tentar_historia_nova(monkeypatch):
    calls = []
    monkeypatch.setattr(generate_daily_batch, "setup_logging", lambda *args: None, raising=False)
    monkeypatch.setattr(generate_daily_batch, "_contar_lote_do_dia", lambda langs: {lang: 0 for lang in langs})
    def outage(*args, **kwargs):
        calls.append(args)
        return 2
    monkeypatch.setattr(generate_daily_batch, "_executar_historia", outage)
    assert generate_daily_batch.main(["--lang", "pt"]) == 2
    assert len(calls) == 1


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
        partes = 2 if len(chamadas) == 1 else 1
        for idioma in idiomas:
            contagens[idioma] += partes
        return 0

    monkeypatch.setattr(generate_daily_batch, "_executar_historia", executar)

    resultado = generate_daily_batch.preencher_lote(["pt", "en", "es"], 3, 6)

    assert resultado == {"pt": 3, "en": 3, "es": 3}
    assert chamadas == [(["pt", "en", "es"], 3), (["pt", "en", "es"], 2)]


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
