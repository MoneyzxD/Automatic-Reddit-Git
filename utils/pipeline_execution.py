"""Política determinística de execução; entradas livres nunca viram shell."""
import os
from pathlib import Path
import re

from utils.pipeline_state import StateError


def resolve_execution(*, event: str, ref: str, run_id: str, state_action: str = "normal",
                      validation_namespace: str = "", dry_run: bool = False,
                      only_generate: bool = False, test_story: bool = False) -> dict:
    if event not in {"workflow_dispatch", "schedule"} or not re.fullmatch(r"[0-9]+", run_id):
        raise StateError("Evento ou identidade de execução inválidos")
    if state_action not in {"normal", "bootstrap", "verify"}:
        raise StateError("Ação de estado inválida")
    if validation_namespace and not re.fullmatch(r"validation-[a-z0-9-]{1,80}", validation_namespace):
        raise StateError("Namespace de validação inválido")
    if any(type(flag) is not bool for flag in (dry_run, only_generate, test_story)):
        raise StateError("Opção de execução inválida")
    if event == "schedule":
        if ref != "refs/heads/main" or validation_namespace or state_action != "normal":
            raise StateError("Cron permitido somente na produção em main")
        dry_run = only_generate = test_story = False
    preview = dry_run or only_generate or test_story
    if state_action != "normal":
        if dry_run:
            raise StateError("Bootstrap/verify não aceitam dry-run")
        namespace = validation_namespace or "production"
        operation = "bootstrap" if state_action == "bootstrap" else "restore"
    elif preview:
        namespace = validation_namespace or f"validation-{run_id}"
        operation = "skip" if dry_run else "bootstrap-validation"
    else:
        if ref != "refs/heads/main" or validation_namespace:
            raise StateError("Publicação permitida somente em main/production")
        namespace, operation = "production", "restore"
    return {"namespace": namespace, "state_action": state_action, "state_operation": operation,
            "generate": state_action == "normal", "publish": state_action == "normal" and not preview,
            "dry_run": dry_run, "test_story": test_story, "required": not dry_run}


def assert_upload_namespace() -> None:
    if os.getenv("PIPELINE_STATE_REQUIRED", "").lower() == "true":
        if os.getenv("PIPELINE_STATE_NAMESPACE") != "production":
            raise StateError("Namespace de validação não pode publicar vídeos")


def _flag(name: str) -> bool:
    value = os.getenv(name, "").lower()
    if value not in {"", "true", "false"}:
        raise StateError("Opção de execução inválida")
    return value == "true"


def main() -> int:
    try:
        result = resolve_execution(event=os.getenv("GITHUB_EVENT_NAME", ""), ref=os.getenv("GITHUB_REF", ""),
                    run_id=os.getenv("GITHUB_RUN_ID", ""), state_action=os.getenv("INPUT_STATE_ACTION") or "normal",
                    validation_namespace=os.getenv("INPUT_VALIDATION_NAMESPACE", ""), dry_run=_flag("INPUT_DRY_RUN"),
                    only_generate=_flag("INPUT_ONLY_GENERATE"), test_story=_flag("INPUT_TEST_STORY"))
        languages = list(dict.fromkeys(os.getenv("INPUT_LANGUAGES", "pt en es").split()))
        if not languages or any(language not in {"pt", "pt-br", "en", "es"} for language in languages):
            raise StateError("Idiomas inválidos")
        result["languages"] = " ".join(languages)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            for name, value in result.items():
                output.write(f"{name}={str(value).lower() if isinstance(value, bool) else value}\n")
        print(f"Execução verificada: namespace={result['namespace']}; ação={result['state_action']}")
        return 0
    except (StateError, KeyError, OSError):
        print("Execução bloqueada: configuração de modo/namespace inválida")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
