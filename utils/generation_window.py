"""Respeita a espera Gemini sem impedir a publicação de vídeos já aprovados."""
from datetime import datetime, timezone
import os
from pathlib import Path


def generation_allowed(not_before: str, *, now: datetime | None = None) -> bool:
    value = not_before.strip()
    if not value:
        return True
    deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if deadline.tzinfo is None:
        raise ValueError("Prazo exige fuso horário")
    return (now or datetime.now(timezone.utc)) >= deadline


def main() -> int:
    try:
        deadline = os.environ.get("GEMINI_RETRY_NOT_BEFORE", "")
        allowed = generation_allowed(deadline)
        with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write(f"allowed={str(allowed).lower()}\n")
        if not allowed:
            print(f"Geração adiada pelo prazo Gemini: {deadline}. Fila aprovada pode ser publicada.")
        else:
            print("Geração liberada pelo prazo configurado; disponibilidade da API ainda será verificada.")
        return 0
    except (ValueError, OSError, KeyError):
        print("Prazo Gemini inválido ou saída indisponível; nenhuma geração liberada.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
