"""
subtitle.py
===========
Gera subtítulos ASS animados palavra por palavra.

Estilo alvo (Imagem 2 — "FINGI"):
    - Palavra por palavra, centralizada
    - UPPERCASE vermelho com outline preto grosso
    - Fonte Impact
    - Animação bounce: 80% -> 115% -> 100%

Pipeline:
    1. Carrega word boundaries do JSON gerado pelo voice.py
    2. Gera ASS com word_timing.py
    3. Se boundaries não disponíveis: usa Whisper como fallback

Whisper apenas como fallback (não é mais a fonte primária de timing).
"""
from __future__ import annotations

import logging
from pathlib import Path

from stages.word_timing import (
    generate_ass,
    load_word_boundaries,
    estimate_word_timestamps,
)

logger = logging.getLogger(__name__)


class SubtitleGenerator:
    """
    Gera arquivos ASS com subtítulos animados word-by-word.
    Fonte primária de timing: word_boundaries do edge-tts.
    Fallback: Whisper ou estimativa fonética.
    """

    def __init__(self, config: dict):
        self.config         = config
        self.model_size     = config.get("whisper_model", "base")
        self.device         = config.get("whisper_device", "cpu")
        self.language_codes = config.get("language_codes", {})
        self._whisper_model = None

    # ── ASS A PARTIR DE WORD BOUNDARIES ─────────────────────────────────

    def generate_from_boundaries(
        self, boundaries_path: Path, output_path: Path
    ) -> bool:
        """Gera ASS a partir do JSON de word boundaries do edge-tts."""
        boundaries = load_word_boundaries(boundaries_path)
        if not boundaries:
            logger.warning("Word boundaries não encontrados: %s", boundaries_path)
            return False

        return generate_ass(boundaries, output_path)

    # ── FALLBACK: WHISPER ────────────────────────────────────────────────

    def _get_whisper_model(self):
        """Carrega Whisper (lazy loading)."""
        if self._whisper_model is None:
            try:
                import stable_whisper as sw
                self._whisper_model = sw.load_model(self.model_size, device=self.device)
                logger.info("Whisper '%s' carregado", self.model_size)
            except ImportError:
                try:
                    import whisper
                    self._whisper_model = whisper.load_model(self.model_size)
                    logger.info("Whisper (base) '%s' carregado", self.model_size)
                except ImportError:
                    logger.error("Whisper não instalado: pip install openai-whisper")
                    raise
        return self._whisper_model

    def _generate_from_whisper(
        self, audio_path: Path, language: str, output_path: Path
    ) -> bool:
        """Usa Whisper para extrair timestamps e gerar ASS."""
        lang_code = self.language_codes.get(language, language)
        try:
            model  = self._get_whisper_model()
            result = model.transcribe(
                str(audio_path), language=lang_code, word_timestamps=True
            )
            # Converter segmentos Whisper em word boundaries
            boundaries = []
            for seg in result.get("segments", []):
                for w in seg.get("words", []):
                    boundaries.append({
                        "word":     w.get("word", "").strip(),
                        "start":    w.get("start", 0),
                        "duration": w.get("end", 0) - w.get("start", 0),
                    })

            if not boundaries:
                raise ValueError("Whisper não retornou word-level timestamps")

            return generate_ass(boundaries, output_path)

        except Exception as e:
            logger.error("Whisper falhou: %s", e)
            return False

    # ── FALLBACK: ESTIMATIVA FONÉTICA ────────────────────────────────────

    def _generate_estimated(
        self, text: str, audio_path: Path, output_path: Path
    ) -> bool:
        """Estima timestamps via modelo fonético quando tudo falha."""
        # Estimar duração do áudio
        duration = 60.0
        try:
            import mutagen.mp3
            duration = float(mutagen.mp3.MP3(str(audio_path)).info.length)
        except Exception:
            pass

        boundaries = estimate_word_timestamps(text, duration)
        if not boundaries:
            return False

        return generate_ass(boundaries, output_path)

    # ── INTERFACE PÚBLICA ─────────────────────────────────────────────────

    def generate(
        self,
        audio_path: Path,
        language: str,
        output_path: Path,
        script_text: str = "",
    ) -> bool:
        """
        Gera arquivo ASS animado word-by-word.

        Ordem de tentativas:
        1. Word boundaries do edge-tts (JSON gerado pelo voice.py)
        2. Whisper word-level timestamps
        3. Estimativa fonética

        output_path deve terminar em .ass
        """
        audio_path  = Path(audio_path)
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 1. Word boundaries do edge-tts
        boundaries_path = audio_path.with_name(audio_path.stem + "_boundaries.json")
        if boundaries_path.exists():
            logger.info("Gerando ASS via edge-tts boundaries: %s", output_path.name)
            if self.generate_from_boundaries(boundaries_path, output_path):
                return True

        # 2. Whisper
        if self.config.get("use_whisper_fallback", False):
            try:
                if self._generate_from_whisper(audio_path, language, output_path):
                    return True
            except Exception as e:
                logger.warning("Whisper indisponível: %s", e)

        # 3. Estimativa fonética
        if script_text:
            logger.warning("Usando estimativa fonética para %s", output_path.name)
            return self._generate_estimated(script_text, audio_path, output_path)

        logger.error("Não foi possível gerar subtítulos para %s", audio_path.name)
        return False

    def generate_batch(self, audio_paths: list, language: str,
                       subtitle_dir: Path, scripts: list = None) -> list:
        """Gera ASS para múltiplos arquivos de áudio."""
        generated = []
        scripts   = scripts or [""] * len(audio_paths)
        for audio_path, script in zip(audio_paths, scripts):
            audio_path = Path(audio_path)
            ass_path   = Path(subtitle_dir) / language / (audio_path.stem + ".ass")
            if self.generate(audio_path, language, ass_path, script):
                generated.append(ass_path)
        return generated
