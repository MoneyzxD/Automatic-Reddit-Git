"""Uma revisão de exemplo sintético público; sem fontes, estado ou YouTube."""
from pathlib import Path
import json
import os
import sys
import time

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from stages.script_guardian import _GroqReviewer, _provider_failure, parse_semantic_review


def main():
    result = {"generation_calls": 0, "model": "gemini-3.5-flash-lite"}
    started = time.monotonic()
    try:
        if (not os.getenv("GEMINI_API_KEY") or os.getenv("PIPELINE_LLM_PROVIDER") != "gemini"
                or os.getenv("GEMINI_MODEL") != result["model"]):
            raise ValueError("Configuração de diagnóstico inválida")
        source = "I prepared dinner, and my friend thanked me."
        context = {"mode": "chunk", "stage": "translation", "language": "pt",
                   "source_text": source, "source_chunk": source,
                   "candidate_text": "Preparei o jantar, e meu amigo me agradeceu.",
                   "profile": {"story_id": "synthetic-public", "narration_gender": "male"},
                   "factual_context": json.dumps([{"kind": "event", "value": source, "source_quote": source}])}
        reviewer = _GroqReviewer({"groq_model": "qwen/qwen3.8-27b", "semantic_timeout_seconds": 60})
        result["generation_calls"] = 1
        outcome = parse_semantic_review(reviewer.review(**context))
        result.update(http_status=200, review_status=outcome.status, issues=len(outcome.issues))
        code = 0 if outcome.approved and not outcome.issues else 2
    except Exception as error:
        failure = _provider_failure(error, "chunk", result["generation_calls"], 0)
        result.update(http_status=failure.http_status,
                      failure_code=failure.code if result["generation_calls"] else "probe_setup_error")
        code = 2
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    print(json.dumps(result))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
