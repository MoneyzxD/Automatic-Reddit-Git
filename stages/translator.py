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
from collections import Counter
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


class LanguageDetectorUnavailable(RuntimeError):
    """O detector local obrigatório não pôde avaliar um corpo elegível."""

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
        limit = chunk_size or self.CHUNK_SIZE
        markers = [(match.start(), match.end()) for match in
                   re.finditer(r"ZXQGLOSSARY\d{6}ZXQ", text)]
        start = 0
        chunks = []
        while start < len(text):
            preview = text[start:min(len(text), start + limit + 2)]
            end = start + split_lossless(preview, limit)[0].end
            for marker_start, marker_end in markers:
                if marker_start < end < marker_end:
                    # Retrocede se há espaço antes da sentinela; se ela começa
                    # no chunk, conserva o marcador inteiro mesmo num limite menor.
                    end = marker_start if marker_start > start else marker_end
                    break
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
    def _without_preserved_spans(source: str, candidate: str,
                                 target_lang: str) -> tuple[str, str]:
        """Remove títulos e nomes copiados de ambos os lados antes de comparar o corpo."""
        title_word = r"[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+"
        connector = r"(?:and|of|the|a|an|to|in|on|for)"
        title_run = re.compile(
            rf"(?<!\w){title_word}(?:[ \t]+(?:{connector}[ \t]+)*{title_word})+(?!\w)"
        )
        phrases = []
        for match in title_run.finditer(source):
            phrase = match.group()
            words = phrase.split()
            title_shape = words[0] in {"The", "An"} or bool(re.search(
                r"\b(?:of|the|in|on|to|for)\b", phrase
            ))
            prefix = source[:match.start()]
            suffix = source[match.end():]
            cue = bool(re.search(r"\b(?:named|called|titled|entitled|read)\s*$", prefix,
                                 re.IGNORECASE))
            delimited = (prefix.rstrip().endswith(('"', "'", "“", "‘")) and
                         suffix.lstrip().startswith(('"', "'", "”", "’")))
            if title_shape:
                # Capitalização isolada no início da frase não prova que é título.
                if cue or delimited:
                    phrases.append((phrase, True))
            else:
                phrases.append((phrase, False))
        for phrase, is_title in phrases:
            pattern = re.compile(
                r"(?<!\w)" + r"\s+".join(map(re.escape, phrase.split())) + r"(?!\w)",
                re.IGNORECASE,
            )
            if is_title and pattern.search(candidate):
                source = pattern.sub(" ", source, count=1)
                candidate = pattern.sub(" ", candidate, count=1)
            elif not is_title:
                names = re.findall(title_word, phrase)
                if all(re.search(rf"(?<!\w){re.escape(name)}(?!\w)", candidate,
                                 re.IGNORECASE) for name in names):
                    connector = {"pt": "e", "es": "y"}.get(target_lang)
                    translated_connector = (re.search(rf"(?<!\w){connector}(?!\w)", candidate,
                                                     re.IGNORECASE) if connector else None)
                    if " and " in phrase and translated_connector:
                        # Conector entre nomes foi traduzido; não entra no corpo.
                        source = pattern.sub(" ", source, count=1)
                        candidate = re.sub(rf"(?<!\w){connector}(?!\w)", " ", candidate,
                                           count=1, flags=re.IGNORECASE)
                    for name in names:
                        name_pattern = rf"(?<!\w){re.escape(name)}(?!\w)"
                        if not (" and " in phrase and translated_connector):
                            source = re.sub(name_pattern, " ", source, count=1,
                                            flags=re.IGNORECASE)
                        candidate = re.sub(name_pattern, " ", candidate, count=1,
                                           flags=re.IGNORECASE)
        return source, candidate

    @staticmethod
    def _detect_target_language(text: str) -> tuple[str, float]:
        """Detecta idioma localmente e sempre com a mesma semente."""
        try:
            from langdetect import DetectorFactory, LangDetectException, detect_langs
        except ImportError as exc:
            raise LanguageDetectorUnavailable("langdetect não instalado") from exc
        DetectorFactory.seed = 0
        try:
            choices = detect_langs(text)
        except LangDetectException as exc:
            raise LanguageDetectorUnavailable("detector sem evidência no corpo elegível") from exc
        except Exception as exc:
            raise LanguageDetectorUnavailable("detector de idioma indisponível") from exc
        if not choices:
            raise LanguageDetectorUnavailable("detector sem evidência no corpo elegível")
        return choices[0].lang, choices[0].prob

    def _candidate_issue(self, source: str, candidate: str, target_lang: str,
                         tokens: dict[str, str]) -> str | None:
        if not candidate.strip():
            return "Chunk traduzido vazio"
        if any(candidate.count(token) != 1 for token in tokens):
            return "Placeholder ausente ou duplicado"
        for token in tokens:
            source = source.replace(token, "")
            candidate = candidate.replace(token, "")
        source, candidate = self._without_preserved_spans(source, candidate, target_lang)
        source_words = re.findall(r"[^\W\d_]+", source.casefold())
        candidate_words = re.findall(r"[^\W\d_]+", candidate.casefold())
        matched = sum((Counter(source_words) & Counter(candidate_words)).values())
        coverage = matched / len(source_words) if source_words else 0.0
        if source_words and (
            source_words == candidate_words or
            (len(source_words) >= 4 and coverage >= 0.75) or
            (len(source_words) == 3 and coverage >= 2 / 3) or
            (len(source_words) == 2 and coverage == 1.0) or
            # Um cognato isolado não basta; exige marcador inglês sem uso em PT/ES.
            (len(source_words) == 2 and bool(
                set(source_words) & set(candidate_words) & {"i", "you", "she", "it", "we", "they", "the"}
            ))
        ):
            return "Chunk permaneceu no idioma fonte"
        # Frases curtas dão falsos positivos no detector; o filtro lexical
        # permanece como única evidência até haver quatro palavras úteis.
        if len(candidate_words) >= 4 and sum(len(word) for word in candidate_words) >= 15:
            detected = self._detect_target_language(candidate)
            if detected and detected[1] >= 0.90 and detected[0] != target_lang:
                return "Idioma alvo não confirmado"
        return None

    def _cached_text_valid(self, source: str, cached: str, source_lang: str,
                           target_lang: str) -> bool:
        if not cached.strip():
            return False
        if source_lang == target_lang:
            return cached == source
        try:
            protected = self.glossary.prepare(source, source_lang, target_lang)
        except GlossaryIntegrityError:
            return False
        if any(token in cached for token in protected.tokens):
            return False
        required = Counter(protected.tokens.values())
        if any(cached.count(term) < count for term, count in required.items()):
            return False
        try:
            return self._candidate_issue(source, cached, target_lang, {}) is None
        except (LanguageDetectorUnavailable, ImportError):
            return False

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
                try:
                    issue = self._candidate_issue(source_core, candidate, target_lang, tokens)
                except (LanguageDetectorUnavailable, ImportError) as exc:
                    return TranslationChunkResult(index, chunk, None, None, "unavailable", str(exc))
                if issue:
                    last_status, last_error = "rejected", issue
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
                    if metadata == expected and self._cached_text_valid(
                        script_text, cached, source_key, lang_key,
                    ):
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
