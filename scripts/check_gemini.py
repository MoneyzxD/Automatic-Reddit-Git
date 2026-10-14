"""Confere o catálogo autenticado sem gerar conteúdo nem expor a chave."""

from pathlib import Path
import os
import re
import sys

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from utils import environment as env
from utils.gemini_client import GeminiError


def check_catalog():
    if env.llm_provider() != "gemini":
        raise ValueError("Consulta de catálogo exige o provedor Gemini")
    key = env.llm_api_key()
    if not key:
        raise GeminiError("invalid_api_key", 401)
    models, token = [], None
    for _ in range(5):
        response = None
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                headers={"x-goog-api-key": key}, params={"pageSize": 100, **({"pageToken": token} if token else {})},
                timeout=30, allow_redirects=False)
            if response.status_code != 200:
                raise GeminiError("catalog_unavailable", response.status_code)
            data = response.json()
            if not isinstance(data, dict) or not isinstance(data.get("models"), list):
                raise GeminiError("invalid_json")
            for model in data["models"]:
                name = model.get("name") if isinstance(model, dict) else None
                if (isinstance(name, str) and re.fullmatch(r"models/gemini-[a-zA-Z0-9._-]{1,80}", name)
                        and "generateContent" in model.get("supportedGenerationMethods", [])):
                    models.append(name.removeprefix("models/"))
            token = data.get("nextPageToken")
            if not token:
                return sorted(set(models))
            if not isinstance(token, str) or len(token) > 4096:
                raise GeminiError("invalid_catalog")
        except (requests.RequestException, ValueError):
            raise GeminiError("catalog_unavailable") from None
        finally:
            if response is not None:
                response.close()
    raise GeminiError("catalog_page_limit")


def main():
    try:
        catalog_only = os.getenv("PIPELINE_GEMINI_CATALOG_ONLY", "").lower() == "true"
        if catalog_only and not os.getenv("PIPELINE_STATE_NAMESPACE", "").startswith("validation-"):
            raise ValueError("Consulta isolada exige namespace de validação")
        models = check_catalog()
        print("Modelos Gemini disponíveis para generateContent: " + ", ".join(models))
        if not catalog_only:
            from utils.gemini_client import GeminiClient
            chosen = GeminiClient(env.llm_api_key(), "preflight").model
            if chosen not in models:
                print("Modelo Gemini configurado ausente no catálogo; nenhuma geração iniciada.")
                return 2
        return 0
    except (GeminiError, ValueError) as error:
        print(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
