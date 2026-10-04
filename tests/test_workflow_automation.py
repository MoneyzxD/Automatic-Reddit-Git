from pathlib import Path
import shlex

import yaml


BASE_DIR = Path(__file__).parent.parent


def pipeline_job():
    return yaml.safe_load((BASE_DIR / ".github/workflows/pipeline.yml").read_text(encoding="utf-8"))["jobs"]["gerar-e-publicar"]


def test_runtime_local_verificado_antes_de_testes_e_geracao():
    job = pipeline_job()
    steps = job["steps"]
    java = next(step for step in steps if step.get("uses") == "actions/setup-java@v6")
    assert java["with"] == {"distribution": "temurin", "java-version": "17"}
    cache = next(step for step in steps if step.get("with", {}).get("path") == ".cache/languagetool")
    assert cache["uses"] == "actions/cache@v4"
    assert cache["with"]["key"] == "languagetool-${{ runner.os }}-${{ runner.arch }}-${{ hashFiles('config/languagetool_runtime.env') }}"
    assert "restore-keys" not in cache["with"]
    server = next(step for step in steps if step.get("id") == "languagetool_server")
    assert server["background"] is True
    args = shlex.split(server["run"])
    assert "-Xms256m" in args and "-Xmx1g" in args
    assert args[args.index("--port") + 1] == "8081"
    assert "--public" not in args and "--allow-origin" not in args
    package = next(step for step in steps if step.get("id") == "languagetool_package")
    health = next(step for step in steps if step.get("id") == "languagetool_health")
    tests = next(step for step in steps if step.get("run") == "python -m pytest tests -q")
    generation = next(step for step in steps if step.get("name") == "Gerar video")
    dependencies = next(step for step in steps if step.get("name") == "Instalar dependencias")
    assert steps.index(java) < steps.index(package) < steps.index(server) < steps.index(health) < steps.index(dependencies) < steps.index(tests) < steps.index(generation)
    assert job["env"]["LANGUAGETOOL_URL"] == "http://127.0.0.1:8081/v2/check"
    assert job["env"]["LANGUAGETOOL_REQUIRED"] == "true"
    health_commands = shlex.split(health["run"])
    assert health_commands[health_commands.index("--expected-version") + 1] == "$LANGUAGETOOL_VERSION"
    assert health_commands[health_commands.index("--required-locales") + 1:health_commands.index("--timeout-seconds")] == ["pt-BR", "en-US", "es"]
    assert health_commands[health_commands.index("--timeout-seconds") + 1] == "120;"
    assert ["cat", "data/logs/languagetool.log"] == health_commands[health_commands.index("cat"):health_commands.index("cat") + 2]
    assert ["exit", "1"] == health_commands[health_commands.index("exit"):health_commands.index("exit") + 2]
    assert "continue-on-error" not in health
    cancellation = next(step for step in steps if step.get("cancel") == "languagetool_server")
    assert "if" not in cancellation
    assert steps[-1] is cancellation


def test_artifact_preserva_relatorios_de_qualidade_e_quarentena():
    logs = next(step for step in pipeline_job()["steps"] if step.get("name") == "Anexar logs")
    paths = logs["with"]["path"].splitlines()
    assert "data/logs/*.jsonl" in paths
    assert "data/quarantine/**/*.json" in paths
    assert logs["with"]["retention-days"] == 14


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

    assert "INPUT_LANGUAGES: ${{ inputs.idiomas || 'pt en es' }}" in workflow
    assert workflow.count("PIPELINE_LANGUAGES: ${{ steps.execution.outputs.languages }}") == 2
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
