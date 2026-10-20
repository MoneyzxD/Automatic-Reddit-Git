"""Uma chamada autorizada do incidente PT; conteúdo permanece fora dos logs."""
from pathlib import Path
import json
import os
import re
import sys
import tempfile
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.pipeline_state import APPROVED_REPO, PrivateStateStore
from utils.pipeline_recovery import file_sha256
from stages.script_guardian import _GroqReviewer, _provider_failure


def main():
    started = time.monotonic()
    result = {"generation_calls": 0, "timeout_seconds": 180}
    try:
        namespace = os.environ.get("PROBE_NAMESPACE", "")
        asset = os.environ.get("PROBE_ASSET_ID", "")
        digest = os.environ.get("PROBE_SHA256", "")
        if (not namespace.startswith("validation-") or not re.fullmatch(r"[0-9]+", asset)
                or not re.fullmatch(r"[a-f0-9]{64}", digest)
                or not os.environ.get("GEMINI_API_KEY")
                or os.environ.get("PIPELINE_LLM_PROVIDER") != "gemini"):
            raise ValueError("Configuração de diagnóstico inválida")
        store = PrivateStateStore(APPROVED_REPO, os.environ.get("PIPELINE_STATE_TOKEN", ""), namespace)
        store.validate_target()
        with tempfile.TemporaryDirectory(prefix="gemini-probe-") as work:
            path = Path(work) / "context.json"
            store._download(int(asset), path, 128 * 1024)
            if file_sha256(path) != digest:
                raise ValueError("Contexto divergente")
            context = json.loads(path.read_text(encoding="utf-8"))
        if (context.get("mode") != "chunk" or context.get("stage") != "split_part"
                or context.get("language") != "pt" or context.get("profile", {}).get("story_id") != "1x6sq3x"):
            raise ValueError("Contexto fora do diagnóstico autorizado")
        reviewer = _GroqReviewer({"groq_model": "qwen/qwen3.8-27b", "semantic_timeout_seconds": 180})
        if reviewer.context_chars(**context) != 8411:
            raise ValueError("Tamanho do contexto divergente")
        result["generation_calls"] = 1
        started = time.monotonic()
        raw = reviewer.review(**context)
        result.update(http_status=200, response_complete=True, response_chars=len(raw))
        code = 0
    except Exception as error:
        failure = _provider_failure(error, "chunk", result["generation_calls"], 8411)
        result.update(failure_code=failure.code if result["generation_calls"] else "probe_setup_error",
                      http_status=failure.http_status, response_complete=False)
        code = 2
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
