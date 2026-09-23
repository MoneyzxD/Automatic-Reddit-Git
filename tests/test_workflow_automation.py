from pathlib import Path

import yaml


BASE_DIR = Path(__file__).parent.parent


def test_cron_diario_fica_protegido_por_chave_de_ativacao():
    workflow = (BASE_DIR / ".github" / "workflows" / "pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert '- cron: "0 9 * * *"' in workflow
    assert "vars.PIPELINE_AUTOMATION_ENABLED == 'true'" in workflow
    assert "vars.YOUTUBE_OAUTH_PUBLISHING_STATUS == 'production'" not in workflow


def test_cron_usa_tres_idiomas_tambem_na_publicacao():
    workflow = (BASE_DIR / ".github" / "workflows" / "pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("inputs.idiomas || 'pt en es'") >= 2
    assert "python scripts/generate_daily_batch.py" in workflow
    assert "vars.DAILY_VIDEO_TARGET || '3'" in workflow
    assert "python publish.py --lang $PIPELINE_LANGUAGES" in workflow
    assert "github.event_name == 'schedule'" in workflow


def test_intervalo_de_producao_nao_usa_valor_temporario():
    config = yaml.safe_load(
        (BASE_DIR / "config" / "publishing.yaml").read_text(encoding="utf-8")
    )

    assert config["growth_plan"]["week_5_plus"]["min_interval_minutes"] == 90


def test_lote_diario_comeca_em_tres_e_mapeia_progressao():
    config = yaml.safe_load(
        (BASE_DIR / "config" / "publishing.yaml").read_text(encoding="utf-8")
    )

    plano = config["daily_video_plan"]
    assert plano["target_per_language"] == 3
    assert plano["maximum_target_per_language"] == 10
    assert plano["max_carryover_parts_next_day"] == 1
    assert plano["planned_steps"] == [3, 4, 5, 6, 8, 10]
    assert plano["interval_minutes_by_target"][10] == 60
