"""Regressão no LanguageTool real do runner, sem chamadas de LLM."""
import os

import pytest

from stages.language_tool import LanguageToolClient


pytestmark = pytest.mark.skipif(not os.getenv("LANGUAGETOOL_URL"),
                                reason="Runtime local de LanguageTool não configurado")


def test_regra_real_nao_introduz_crase_em_todas_as_vezes():
    client = LanguageToolClient({})
    client.health()
    text = "Falhei todas as vezes."
    with client._post(text, "pt-BR") as response:
        response.raise_for_status()
        raw = response.json()
    assert any(match["rule"]["id"] == "AS_VEZES_BR" for match in raw["matches"])
    assert not any(issue.rule_id == "AS_VEZES_BR" for issue in client.check(text, "pt"))


def test_regra_real_continua_detectando_crase_ausente():
    client = LanguageToolClient({})
    findings = client.check("Eu as vezes fico triste.", "pt")
    assert any(issue.rule_id == "AS_VEZES_BR" and "às vezes" in issue.replacements
               for issue in findings)
