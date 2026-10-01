"""
translator.py
=============
Estágio dedicado de tradução do script para PT-BR, EN e ES.

Fluxo:
    1. Detecta idioma original do script
    2. Traduz para cada idioma alvo
    3. Rejeita qualquer bloco vazio, inalterado ou com marcador perdido
    4. Salva apenas scripts aprovados e retorna resultados tipados

Stack gratuita (sem API key):
    Primário  : deep-translator (GoogleTranslator — gratuito)
    Fallback  : deep-translator (MyMemoryTranslator — gratuito, mesmo pacote)
    Nota: googletrans (o pacote separado, nao o motor do deep-translator)
    foi descartado de proposito — ele fixa httpx numa versao de 2020,
    incompativel com groq/python-telegram-bot/huggingface-hub. MyMemory
    e um segundo motor real sem esse conflito, ja incluso no deep-translator.

Instalação:
    pip install deep-translator
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from stages.contextual_glossary import ContextualGlossary, GlossaryIntegrityError
from utils.text_chunks import split_lossless

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranslationChunkResult:
    index: int
    source_text: str
    translated_text: str | None
    provider: str | None
    status: Literal["approved", "rejected", "unavailable"]
    error: str = ""


@dataclass(frozen=True)
class TranslationResult:
    status: Literal["approved", "rejected", "unavailable"]
    text: str | None
    provider: str | None
    source_lang: str
    target_lang: str
    chunks: tuple[TranslationChunkResult, ...]
    error: str = ""

    def require_text(self) -> str:
        if self.status != "approved" or self.text is None:
            raise TranslationFailed(self)
        return self.text


class TranslationFailed(RuntimeError):
    def __init__(self, result: TranslationResult):
        super().__init__(result.error or "Tradução não aprovada")
        self.result = result

# Mapeamento de idioma para código Google Translate
LANG_CODES = {
    "pt":    "pt",
    "en":    "en",
    "es":    "es",
}

# MyMemory exige codigo COM regiao (en-US, nao "en" sozinho) — "en" sozinho
# da erro "No support for the provided language" mesmo sendo idioma valido.
# Mapeamento separado do LANG_CODES acima porque o GoogleTranslator aceita
# os codigos simples normalmente e nao deve ser mexido.
MYMEMORY_LANG_CODES = {
    "pt": "pt-BR",
    "en": "en-US",
    "es": "es-MX",
}

LANG_NAMES = {
    "pt":    "Português (Brasil)",
    "en":    "English",
    "es":    "Español",
}

# Normaliza chave de idioma para nome de pasta/arquivo interno
# pt-br → pt para evitar conflitos de cache e compatibilidade
def _normalize_lang_key(lang: str) -> str:
    """Normaliza idioma para uso interno em pastas e arquivos."""
    return "pt" if lang == "pt-br" else lang


def _ensure_utf8(text: str) -> str:
    """Garante que o texto está em UTF-8 correto."""
    if isinstance(text, str):
        try:
            # Tenta recodificar para garantir UTF-8 válido
            text = text.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
        except Exception:
            pass
    return text


class ScriptTranslator:
    """
    Traduz scripts de narração para múltiplos idiomas.
    Divide o texto em chunks para contornar limite do Google Translate.
    """

    CHUNK_SIZE = 4500   # chars por request (limite seguro do Google)
    DELAY      = 1.0    # segundos entre requests

    # Retry quando os DOIS motores falham na mesma rodada — geralmente
    # transitorio (rate limit, hiccup do servidor). len() define quantas
    # tentativas extras alem da primeira.
    TRANSLATE_MAX_TENTATIVAS = 3
    TRANSLATE_RETRY_ESPERA   = [5, 15]

    def __init__(self, config: dict = None, glossary: ContextualGlossary | None = None):
        self.config      = config or {}
        self.scripts_dir = None  # definido em translate_all()
        self.glossary = glossary or ContextualGlossary.from_path(
            Path(__file__).parent.parent / "config" / "contextual_glossary.yaml"
        )

    # ── DETECÇÃO DE IDIOMA ────────────────────────────────────────────────

    def detect_language(self, text: str) -> str:
        """
        Detecta o idioma do texto.
        Retorna código ISO ('en', 'pt', 'es').
        """
        sample = text[:500]
        try:
            from deep_translator import GoogleTranslator
            GoogleTranslator(source="auto", target="en").translate(sample)
            pt_words = ["não", "você", "que", "uma", "para", "com", "meu", "foi"]
            es_words = ["que", "una", "para", "con", "fue", "pero", "porque", "cuando"]
            en_words = ["the", "and", "that", "was", "for", "with", "have", "this"]

            lower    = sample.lower()
            pt_score = sum(1 for w in pt_words if f" {w} " in lower)
            es_score = sum(1 for w in es_words if f" {w} " in lower)
            en_score = sum(1 for w in en_words if f" {w} " in lower)

            if pt_score > es_score and pt_score > en_score:
                return "pt"
            elif es_score > pt_score and es_score > en_score:
                return "es"
            else:
                return "en"
        except Exception:
            return "en"

    # ── TRADUÇÃO ──────────────────────────────────────────────────────────

    def _split_chunks(self, text: str, chunk_size: int | None = None) -> list:
        """Divide sem perder separadores nem partir uma sentinela."""
        raw_chunks = split_lossless(text, chunk_size or self.CHUNK_SIZE)
        boundaries = {chunk.end for chunk in raw_chunks}
        for marker in re.finditer(r"ZXQGLOSSARY\d{6}ZXQ", text):
            boundaries = {end for end in boundaries if not marker.start() < end < marker.end()}
        start = 0
        chunks = []
        for end in sorted(boundaries):
            chunks.append(text[start:end])
            start = end
        return chunks

    # MyMemory (API gratuita por tras do deep-translator) limita ~500
    # caracteres por requisicao — bem menor que o CHUNK_SIZE do Google
    # Translate. Margem de seguranca pra nao estourar em textos com
    # acentuacao (alguns caracteres multibyte contam mais pro limite real).
    MYMEMORY_CHUNK_SIZE = 450

    def _translate_chunk_google(self, chunk: str, source: str, target: str) -> str | None:
        try:
            from deep_translator import GoogleTranslator
            return GoogleTranslator(source=LANG_CODES.get(source, source),
                                    target=LANG_CODES.get(target, target)).translate(chunk)
        except Exception as exc:
            logger.warning("Google falhou (%s→%s): %s", source, target, exc)
            return None

    def _translate_chunk_mymemory(self, chunk: str, source: str, target: str) -> str | None:
        try:
            from deep_translator import MyMemoryTranslator
            return MyMemoryTranslator(source=MYMEMORY_LANG_CODES.get(source, source),
                                      target=MYMEMORY_LANG_CODES.get(target, target)).translate(chunk)
        except Exception as exc:
            logger.warning("MyMemory falhou (%s→%s): %s", source, target, exc)
            return None

    @staticmethod
    def _target_language_ok(text: str, source_lang: str, target_lang: str) -> bool:
        # Sentinelas não são evidência de idioma.
        text = re.sub(r"ZXQGLOSSARY\d{6}ZXQ", "", text)
        words = re.findall(r"[^\W\d_]+", text.casefold(), re.UNICODE)
        if len(words) < 4:
            return True
        markers = {
            "en": {"i", "to", "the", "and", "with", "that", "this", "were", "they",
                   "have", "from", "went", "was", "is"},
            "pt": {"que", "uma", "com", "para", "não", "estava", "minha", "isso", "você"},
            "es": {"que", "una", "con", "para", "estaba", "esto", "usted", "pero", "cuando"},
        }
        source_hits = sum(word in markers.get(source_lang, set()) for word in words)
        target_hits = sum(word in markers.get(target_lang, set()) for word in words)
        return not (source_hits >= 1 and target_hits == 0)

    def _translate_one_chunk(self, index: int, chunk: str, source_lang: str,
                             target_lang: str, tokens: dict[str, str]) -> TranslationChunkResult:
        if not chunk.strip():
            return TranslationChunkResult(index, chunk, chunk, "identity", "approved")
        leading = chunk[:len(chunk) - len(chunk.lstrip())]
        trailing = chunk[len(chunk.rstrip()):]
        source_core = chunk.strip()
        waits = self.config.get("retry_waits", self.TRANSLATE_RETRY_ESPERA)
        last_status = "unavailable"
        last_error = "Provedores indisponíveis"
        for attempt in range(self.TRANSLATE_MAX_TENTATIVAS):
            if attempt:
                time.sleep(waits[attempt - 1])
            for provider, method in (("Google", self._translate_chunk_google),
                                     ("MyMemory", self._translate_chunk_mymemory)):
                candidate = method(source_core, source_lang, target_lang)
                if candidate is None:
                    continue
                candidate = _ensure_utf8(candidate).strip()
                if not candidate.strip():
                    last_status, last_error = "rejected", "Chunk traduzido vazio"
                    continue
                missing = [token for token in tokens if candidate.count(token) != 1]
                if missing:
                    last_status, last_error = "rejected", "Placeholder ausente ou duplicado"
                    continue
                remaining_source = source_core
                for token in tokens:
                    remaining_source = remaining_source.replace(token, "")
                remaining_candidate = candidate
                for token in tokens:
                    remaining_candidate = remaining_candidate.replace(token, "")
                source_words = re.findall(r"[^\W\d_]+", remaining_source.casefold())
                candidate_words = re.findall(r"[^\W\d_]+", remaining_candidate.casefold())
                unchanged_words = sum(left == right for left, right in
                                      zip(source_words, candidate_words))
                mostly_unchanged = (
                    len(source_words) >= 4
                    and unchanged_words / max(len(source_words), len(candidate_words)) >= 0.75
                )
                if source_words and (source_words == candidate_words or mostly_unchanged):
                    last_status, last_error = "rejected", "Chunk permaneceu no idioma fonte"
                    continue
                if not self._target_language_ok(candidate, source_lang, target_lang):
                    last_status, last_error = "rejected", "Idioma alvo não confirmado"
                    continue
                return TranslationChunkResult(index, chunk, leading + candidate + trailing,
                                              provider, "approved")
        return TranslationChunkResult(index, chunk, None, None, last_status, last_error)

    def translate(self, text: str, source_lang: str, target_lang: str) -> TranslationResult:
        source = _normalize_lang_key(source_lang)
        target = _normalize_lang_key(target_lang)
        if not text.strip():
            return TranslationResult("rejected", None, None, source_lang, target_lang, (),
                                     "Fonte vazia")
        if source == target:
            return TranslationResult("approved", text, "identity", source_lang, target_lang,
                                     (TranslationChunkResult(0, text, text, "identity", "approved"),))
        try:
            protected = self.glossary.prepare(text, source, target)
        except GlossaryIntegrityError as exc:
            return TranslationResult("rejected", None, None, source_lang, target_lang, (), str(exc))
        chunks = self._split_chunks(protected.text, chunk_size=self.MYMEMORY_CHUNK_SIZE)
        results = []
        for index, chunk in enumerate(chunks):
            tokens = {token: value for token, value in protected.tokens.items() if token in chunk}
            result = self._translate_one_chunk(index, chunk, source, target, tokens)
            results.append(result)
            if result.status != "approved":
                return TranslationResult(result.status, None, None, source_lang, target_lang,
                                         tuple(results), result.error)
            if index < len(chunks) - 1:
                time.sleep(self.config.get("delay", self.DELAY))
        translated = "".join(part.translated_text or "" for part in results)
        try:
            translated = self.glossary.restore(translated, protected)
        except GlossaryIntegrityError as exc:
            return TranslationResult("rejected", None, None, source_lang, target_lang,
                                     tuple(results), str(exc))
        providers = {part.provider for part in results if part.provider != "identity"}
        provider = next(iter(providers)) if len(providers) == 1 else "mixed"
        return TranslationResult("approved", translated, provider, source_lang, target_lang,
                                 tuple(results))

    # ── PIPELINE PRINCIPAL ────────────────────────────────────────────────

    def translate_all(
        self,
        script_text: str,
        story_id: str,
        scripts_dir: Path,
        languages: list[str],
        source_lang: str | None = None,
        force: bool = False,
    ) -> dict[str, TranslationResult]:
        """Traduz idiomas pedidos e persiste apenas resultados integrais aprovados."""
        if not script_text.strip():
            raise TranslationFailed(TranslationResult(
                "rejected", None, None, source_lang or "", languages[0] if languages else "",
                (), "Fonte vazia",
            ))
        if not source_lang:
            source_lang = self.detect_language(script_text)
        source_key = _normalize_lang_key(source_lang)
        source_hash = hashlib.sha256(script_text.encode("utf-8")).hexdigest()
        results: dict[str, TranslationResult] = {}

        for lang in languages:
            lang_key = _normalize_lang_key(lang)
            lang_dir = scripts_dir / lang_key
            script_path = lang_dir / f"script_{story_id}_{lang_key}.txt"
            cache_path = script_path.with_suffix(".cache.json")
            expected = {"source_sha256": source_hash, "source_lang": source_key,
                        "target_lang": lang_key, "glossary_version": self.glossary.version}
            if not force and script_path.is_file() and cache_path.is_file():
                try:
                    metadata = json.loads(cache_path.read_text(encoding="utf-8"))
                    cached = script_path.read_text(encoding="utf-8")
                    if metadata == expected and cached.strip():
                        results[lang] = TranslationResult("approved", cached, "cache",
                                                          source_lang, lang, ())
                        continue
                except (OSError, ValueError):
                    pass
            result = self.translate(script_text, source_lang, lang)
            translated = result.require_text()
            lang_dir.mkdir(parents=True, exist_ok=True)
            self._write_atomic(script_path, translated)
            self._write_atomic(cache_path, json.dumps(expected, ensure_ascii=False))
            results[lang] = result

        return results

    @staticmethod
    def _write_atomic(path: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=f".{path.name}.", suffix=".tmp",
                                         delete=False) as handle:
            temporary = Path(handle.name)
            try:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
            except Exception:
                temporary.unlink(missing_ok=True)
                raise
        try:
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)

    def translate_title(self, title: str, source_lang: str, target_lang: str) -> str:
        """Traduz o título pelo mesmo contrato de aprovação do roteiro."""
        return self.translate(title, source_lang, target_lang).require_text()
