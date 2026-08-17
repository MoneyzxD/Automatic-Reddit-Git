"""
translator.py
=============
Estágio dedicado de tradução do script para PT-BR, EN e ES.

Fluxo:
    1. Detecta idioma original do script
    2. Traduz para cada idioma alvo
    3. Salva arquivos separados: script_pt.txt / script_en.txt / script_es.txt
    4. Retorna dict com scripts prontos por idioma

Stack gratuita (sem API key):
    Primário  : deep-translator (GoogleTranslator — gratuito)
    Fallback  : googletrans 4.0.0rc1
    Fallback 2: script original sem tradução (apenas para EN)

Instalação:
    pip install deep-translator
"""
from __future__ import annotations

import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# Mapeamento de idioma para código Google Translate
LANG_CODES = {
    "pt":    "pt",
    "en":    "en",
    "es":    "es",
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

    def __init__(self, config: dict = None):
        self.config      = config or {}
        self.scripts_dir = None  # definido em translate_all()

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

    def _split_chunks(self, text: str) -> list:
        """
        Divide o texto em chunks menores respeitando parágrafos.
        Evita cortar frases no meio.
        """
        paragraphs = text.split("\n\n")
        chunks     = []
        current    = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 <= self.CHUNK_SIZE:
                current += ("\n\n" if current else "") + para
            else:
                if current:
                    chunks.append(current)
                if len(para) > self.CHUNK_SIZE:
                    sentences = re.split(r"(?<=[.!?])\s+", para)
                    buf = ""
                    for sent in sentences:
                        if len(buf) + len(sent) <= self.CHUNK_SIZE:
                            buf += (" " if buf else "") + sent
                        else:
                            if buf:
                                chunks.append(buf)
                            buf = sent
                    if buf:
                        chunks.append(buf)
                    current = ""
                else:
                    current = para

        if current:
            chunks.append(current)

        return chunks

    def _translate_deep(self, text: str, source: str, target: str) -> str | None:
        """Traduz usando deep-translator (GoogleTranslator)."""
        try:
            from deep_translator import GoogleTranslator
        except ImportError:
            return None

        try:
            chunks     = self._split_chunks(text)
            translated = []
            src_code   = LANG_CODES.get(source, source)
            tgt_code   = LANG_CODES.get(target, target)

            translator = GoogleTranslator(source=src_code, target=tgt_code)

            for i, chunk in enumerate(chunks):
                if not chunk.strip():
                    translated.append(chunk)
                    continue
                result = translator.translate(chunk)
                # Garantir UTF-8 correto na tradução
                result = _ensure_utf8(result) if result else chunk
                translated.append(result or chunk)
                if i < len(chunks) - 1:
                    time.sleep(self.DELAY)

            final_result = "\n\n".join(translated)
            return _ensure_utf8(final_result)

        except Exception as e:
            logger.warning(f"deep-translator falhou ({source}→{target}): {e}")
            return None

    def _translate_googletrans(self, text: str, source: str, target: str) -> str | None:
        """Fallback: googletrans."""
        try:
            from googletrans import Translator
            tr      = Translator()
            chunks  = self._split_chunks(text)
            results = []
            tgt     = LANG_CODES.get(target, target)
            for chunk in chunks:
                r = tr.translate(chunk, src=source, dest=tgt)
                result_text = _ensure_utf8(r.text) if r.text else chunk
                results.append(result_text)
                time.sleep(self.DELAY)
            final_result = "\n\n".join(results)
            return _ensure_utf8(final_result)
        except Exception as e:
            logger.warning(f"googletrans falhou ({source}→{target}): {e}")
            return None

    def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Traduz texto do idioma fonte para o alvo.
        Se source == target, retorna o texto original.
        Tenta deep-translator → googletrans → texto original.
        """
        # Normaliza para comparação (pt-br == pt)
        src_norm = _normalize_lang_key(source_lang)
        tgt_norm = _normalize_lang_key(target_lang)

        if src_norm == tgt_norm:
            logger.info(f"  Idioma já é {target_lang} — sem tradução necessária")
            return text

        logger.info(
            f"  Traduzindo {LANG_NAMES.get(source_lang, source_lang)} → "
            f"{LANG_NAMES.get(target_lang, target_lang)}"
        )

        result = self._translate_deep(text, source_lang, target_lang)
        if result:
            logger.info(f"  ✓ Tradução concluída (deep-translator)")
            return result

        result = self._translate_googletrans(text, source_lang, target_lang)
        if result:
            logger.info(f"  ✓ Tradução concluída (googletrans fallback)")
            return result

        logger.error(
            f"  Tradução falhou ({source_lang}→{target_lang}). "
            f"Instale: pip install deep-translator\n"
            f"  Usando texto original."
        )
        return text

    # ── PIPELINE PRINCIPAL ────────────────────────────────────────────────

    def translate_all(
        self,
        script_text: str,
        story_id: str,
        scripts_dir: Path,
        languages: list,
        source_lang: str = None,
        force: bool = False,
    ) -> dict:
        """
        Traduz o script para todos os idiomas e salva arquivos separados.

        Retorna dict: { "pt-br": "texto...", "en": "texto...", "es": "texto..." }
        Salva:        scripts_dir/{lang_key}/script_{story_id}_{lang_key}.txt

        Nota: pt-br é normalizado para pt internamente (pasta e arquivo),
        mas a chave do dict retornado preserva o idioma original passado.

        force=True ignora o cache em disco e traduz de novo mesmo se o arquivo
        já existir — usado em --test-story, onde o story_id é sempre o mesmo e
        um cache antigo esconderia qualquer mudança nos estágios seguintes.
        """
        if not source_lang:
            source_lang = self.detect_language(script_text)
            logger.info(f"Idioma detectado: {LANG_NAMES.get(source_lang, source_lang)}")

        results = {}

        for lang in languages:
            # Normaliza para nome de pasta/arquivo (pt-br → pt)
            lang_key    = _normalize_lang_key(lang)
            lang_dir    = scripts_dir / lang_key
            lang_dir.mkdir(parents=True, exist_ok=True)
            script_path = lang_dir / f"script_{story_id}_{lang_key}.txt"

            if script_path.exists() and not force:
                logger.info(f"  Script {lang} já existe — carregando")
                results[lang] = script_path.read_text(encoding="utf-8")
                continue

            translated    = self.translate(script_text, source_lang, lang)
            # Garantir UTF-8 correto antes de salvar
            translated    = _ensure_utf8(translated)
            results[lang] = translated
            script_path.write_text(translated, encoding="utf-8")
            logger.info(f"  Salvo: {script_path.name}")

        return results

    def translate_title(self, title: str, source_lang: str, target_lang: str) -> str:
        """
        Traduz apenas o título para o idioma alvo.
        Usado para gerar o nome do arquivo de export.
        """
        src_norm = _normalize_lang_key(source_lang)
        tgt_norm = _normalize_lang_key(target_lang)

        if src_norm == tgt_norm:
            return title
        try:
            from deep_translator import GoogleTranslator
            tgt    = LANG_CODES.get(target_lang, target_lang)
            src    = LANG_CODES.get(source_lang, source_lang)
            result = GoogleTranslator(source=src, target=tgt).translate(title)
            # Garantir UTF-8 correto
            result = _ensure_utf8(result) if result else title
            return result or title
        except Exception as e:
            logger.warning(f"Falha ao traduzir título ({source_lang}→{target_lang}): {e}")
            return title