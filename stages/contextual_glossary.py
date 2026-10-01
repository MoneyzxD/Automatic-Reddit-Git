"""Proteção de conceitos cuja tradução depende do contexto."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ProtectedText:
    text: str
    tokens: dict[str, str]
    glossary_version: str


class GlossaryIntegrityError(RuntimeError):
    """Um conceito ambíguo ou um marcador inválido impede a tradução."""


class ContextualGlossary:
    def __init__(self, version: str, concepts: dict):
        self.version = str(version)
        self.concepts = concepts

    @classmethod
    def from_path(cls, path: Path) -> ContextualGlossary:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not data.get("version") or not isinstance(data.get("concepts"), dict):
            raise ValueError("Glossário contextual inválido")
        return cls(data["version"], data["concepts"])

    def prepare(self, source_text: str, source_lang: str, target_lang: str) -> ProtectedText:
        target_lang = "pt" if target_lang == "pt-br" else target_lang
        if source_lang != "en" or target_lang not in {"pt", "es"}:
            return ProtectedText(source_text, {}, self.version)

        patterns = []
        for concept in self.concepts.values():
            target = concept.get("targets", {}).get(target_lang)
            if target:
                patterns.extend((source, target) for source in concept["source_patterns"])
        # A alternativa mais longa prevalece quando dois padrões se sobrepõem.
        patterns.sort(key=lambda pair: len(pair[0]), reverse=True)
        choices = "|".join(re.escape(source) for source, _ in patterns)
        matcher = re.compile(rf"(?<!\w)(?:{choices}|card)(?!\w)", re.IGNORECASE)
        targets = {source.casefold(): target for source, target in patterns}
        tokens: dict[str, str] = {}

        def replace(match: re.Match[str]) -> str:
            source = match.group().casefold()
            if source == "card":
                raise GlossaryIntegrityError("card isolado é ambíguo")
            index = len(tokens)
            token = f"ZXQGLOSSARY{index:06d}ZXQ"
            while token in source_text or token in tokens:
                index += 1
                token = f"ZXQGLOSSARY{index:06d}ZXQ"
            tokens[token] = targets[source]
            return token

        return ProtectedText(matcher.sub(replace, source_text), tokens, self.version)

    def restore(self, translated_text: str, protected: ProtectedText) -> str:
        if protected.glossary_version != self.version:
            raise GlossaryIntegrityError("Versão do glossário mudou durante a tradução")
        for token in protected.tokens:
            if translated_text.count(token) != 1:
                raise GlossaryIntegrityError(f"Placeholder ausente ou duplicado: {token}")
        for token, target in protected.tokens.items():
            translated_text = translated_text.replace(token, target)
        return translated_text
