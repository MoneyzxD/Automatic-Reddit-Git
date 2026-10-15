"""Uma sonda pública EN, mesmo modelo de produção, sem retry ou dados privados."""
from pathlib import Path
import json
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils.environment import groq_api_key


def safe_error(error):
    """Preserva somente enums, números e indicadores fixos; nunca a mensagem."""
    status = getattr(error, "status_code", None)
    result = {"http_status": status if type(status) is int and 100 <= status <= 599 else None}
    body = getattr(error, "body", None)
    result["body_kind"] = "object" if isinstance(body, dict) else "text" if isinstance(body, str) else "other"
    if isinstance(body, str) and len(body) <= 65536:
        try:
            body = json.loads(body)
        except ValueError:
            body = None
    detail = body.get("error", body) if isinstance(body, dict) else {}
    detail = detail if isinstance(detail, dict) else {}
    known = {"rate_limit_exceeded", "insufficient_quota", "billing_limit_exceeded",
             "model_capacity_exceeded", "invalid_api_key", "model_not_found", "invalid_request_error"}
    code = detail.get("code")
    result["provider_code"] = code if isinstance(code, str) and code in known else "other"
    message = detail.get("message")
    message = message if isinstance(message, str) and len(message) <= 65536 else ""
    result["limit_types"] = sorted(set(re.findall(r"\b(?:TPM|TPD|RPM|RPD|ITPM|OTPM)\b", message)))
    for label in ("Limit", "Used", "Requested"):
        match = re.search(rf"\b{label}\s*[:=]?\s*(\d+(?:\.\d+)?)", message, re.IGNORECASE)
        if match and len(match[1]) <= 15:
            value = float(match[1])
            if value <= 10**12:
                result[label.lower()] = value
    for name, words in {"mentions_daily": ("per day", "daily", "TPD", "RPD"),
                        "mentions_capacity": ("capacity", "overload"),
                        "mentions_traffic": ("traffic", "too many"),
                        "mentions_billing": ("billing", "payment", "credit"),
                        "mentions_organization": ("organization",)}.items():
        result[name] = any(word.casefold() in message.casefold() for word in words)
    return result


def main():
    from groq import Groq
    key = groq_api_key("en")
    if not key:
        print(json.dumps({"credential": "missing", "llm_calls": 0}))
        return 2
    result = {"model": "qwen/qwen3.8-27b", "llm_calls": 1, "private_content_sent": False}
    try:
        with Groq(api_key=key, max_retries=0, timeout=30) as client:
            response = client.chat.completions.create(
                model=result["model"], temperature=0, reasoning_effort="none",
                max_completion_tokens=2048,
                messages=[{"role": "user", "content": "Reply with the single word OK."}],
            )
        result["http_status"] = 200
        usage = response.usage
        result["usage"] = {name: getattr(usage, name) for name in
                           ("prompt_tokens", "completion_tokens", "total_tokens")
                           if type(getattr(usage, name, None)) is int}
        reason = response.choices[0].finish_reason
        result["finish_reason"] = reason if reason in {"stop", "length", "content_filter"} else "other"
    except Exception as error:
        result.update(safe_error(error))
    print(json.dumps(result))
    return 0 if result["http_status"] == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())
