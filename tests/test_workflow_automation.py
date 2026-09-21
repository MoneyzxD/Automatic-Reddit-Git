from pathlib import Path

import yaml


BASE_DIR = Path(__file__).parent.parent


def test_cron_diario_fica_protegido_por_chave_de_ativacao():
    workflow = (BASE_DIR / ".github" / "workflows" / "pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert '- cron: "0 9 * * *"' in workflow
    assert "vars.PIPELINE_AUTOMATION_ENABLED == 'true'" in workflow
    assert "vars.YOUTUBE_OAUTH_PUBLISHING_STATUS == 'production'" in workflow


def test_cron_usa_tres_idiomas_tambem_na_publicacao():
    workflow = (BASE_DIR / ".github" / "workflows" / "pipeline.yml").read_text(
        encoding="utf-8"
    )

    assert workflow.count("inputs.idiomas || 'pt en es'") >= 2
    assert "python publish.py --lang $PIPELINE_LANGUAGES" in workflow
    assert "github.event_name == 'schedule'" in workflow


def test_intervalo_de_producao_nao_usa_valor_temporario():
    config = yaml.safe_load(
        (BASE_DIR / "config" / "publishing.yaml").read_text(encoding="utf-8")
    )

    assert config["growth_plan"]["week_5_plus"]["min_interval_minutes"] == 90
