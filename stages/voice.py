"""
voice.py
========
Geracao de narracao com pacing natural e extracao de timestamps.

Stack gratuita:
    Primario : edge-tts v7.x (voz natural)
    Fallback : gTTS

Timestamps: faster-whisper CUDA via word_timing.py

Selecao de voz por genero:
    female / unknown -> voz primary  (ex: pt-BR-FranciscaNeural)
    male             -> voz secondary (ex: pt-BR-AntonioNeural)
"""
from __future__ import annotations

import logging
from pathlib import Path

from stages.word_timing import (
    generate_audio_with_timestamps,
    estimate_word_timestamps,
    save_word_boundaries,
)

logger = logging.getLogger(__name__)


class VoiceGenerator:

    def __init__(self, config: dict):
        self.config      = config
        self.voices      = config.get("voices", {})
        self.speech_rate = config.get("speech_rate", "+4%")
        # False = usa edge-tts + whisper (producao)
        # True  = forca gTTS (emergencia)
        self.force_gtts  = config.get("force_gtts", False)

    def _add_natural_pauses(self, text: str) -> str:
        """Insere pausas naturais entre paragrafos."""
        return text.replace("\n\n", "\n. \n")

    def _select_voice(self, language: str, narrator_gender: str) -> tuple[str, str]:
        """
        Retorna (voz_principal, voz_secundaria) baseado no genero detectado.
        female / unknown -> primary
        male             -> secondary (troca primary e secondary)
        """
        lang_key    = "pt" if language == "pt-br" else language
        lang_config = self.voices.get(lang_key, {})
        primary     = lang_config.get("primary", "pt-BR-FranciscaNeural")
        secondary   = lang_config.get("secondary", "pt-BR-AntonioNeural")

        if narrator_gender == "male":
            logger.info("Voz selecionada: %s (genero=male)", secondary)
            return secondary, primary
        else:
            logger.info("Voz selecionada: %s (genero=%s)", primary, narrator_gender)
            return primary, secondary

    def _gtts_generate(self, text: str, language: str, output_path: Path) -> bool:
        """Gera audio com gTTS (fallback)."""
        try:
            from gtts import gTTS
        except ImportError:
            logger.error("gTTS nao instalado: pip install gTTS")
            return False

        lang_map = {"pt": "pt", "pt-br": "pt", "en": "en", "es": "es"}
        tld_map  = {"pt": "com.br", "pt-br": "com.br", "en": "com", "es": "com.mx"}

        try:
            tts = gTTS(
                text=text,
                lang=lang_map.get(language, "en"),
                tld=tld_map.get(language, "com"),
                slow=True,
            )
            tts.save(str(output_path))
            logger.info("Audio gerado (gTTS fallback): %s", output_path.name)
            return True
        except Exception as e:
            logger.error("gTTS falhou: %s", e)
            return False

    def _edge_tts_generate(
        self,
        text: str,
        language: str,
        output_path: Path,
        narrator_gender: str = "female",
    ) -> tuple[bool, list]:
        """
        Gera audio via edge-tts v7.x e extrai timestamps word-level reais
        usando faster-whisper com CUDA.
        Retorna (sucesso, boundaries).
        """
        voice, fallback_voice = self._select_voice(language, narrator_gender)

        success, boundaries = generate_audio_with_timestamps(
            text, voice, self.speech_rate, output_path, language=language
        )
        if not success and fallback_voice:
            logger.info("Tentando voz alternativa: %s", fallback_voice)
            success, boundaries = generate_audio_with_timestamps(
                text, fallback_voice, self.speech_rate, output_path, language=language
            )
        return success, boundaries

    def generate(
        self,
        text: str,
        language: str,
        output_path: Path,
        narrator_gender: str = "female",
    ) -> bool:
        """
        Gera MP3 + JSON de timestamps.

        Args:
            text:            Script narrado
            language:        Idioma (pt / en / es)
            output_path:     Caminho de saida do .mp3
            narrator_gender: Genero do narrador (female / male / unknown)

        Fluxo producao:
            1. edge-tts v7.x  -> audio natural
            2. faster-whisper -> timestamps word-level reais (CUDA)
            3. gTTS           -> fallback se edge-tts falhar
            4. estimativa     -> fallback se whisper falhar
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        json_path   = output_path.with_name(output_path.stem + "_boundaries.json")

        boundaries = []
        success    = False

        if not self.force_gtts:
            # edge-tts como primario
            prepared = self._add_natural_pauses(text)
            success, boundaries = self._edge_tts_generate(
                prepared, language, output_path, narrator_gender
            )
            if not success:
                logger.warning("edge-tts falhou — usando gTTS como fallback")

        if not success:
            success = self._gtts_generate(text, language, output_path)
            if success and not boundaries:
                duration   = self._get_mp3_duration(output_path)
                boundaries = estimate_word_timestamps(text, duration)

        # Salvar timestamps
        if boundaries:
            save_word_boundaries(boundaries, json_path)
            logger.info(
                "Timestamps salvos: %s (%d palavras)", json_path.name, len(boundaries)
            )
        else:
            logger.warning("Nenhum timestamp gerado para %s", output_path.name)

        return success

    def _get_mp3_duration(self, mp3_path: Path) -> float:
        """Retorna duracao do MP3 em segundos."""
        try:
            import mutagen.mp3
            return float(mutagen.mp3.MP3(str(mp3_path)).info.length)
        except Exception:
            pass
        try:
            return mp3_path.stat().st_size / (128 * 1024 / 8)
        except Exception:
            return 60.0

    def get_boundaries_path(self, audio_path: Path) -> Path:
        audio_path = Path(audio_path)
        return audio_path.with_name(audio_path.stem + "_boundaries.json")

    def generate_batch(self, parts: list, language: str, audio_dir: Path) -> list:
        generated = []
        for part in parts:
            story_id = part.get("id", "unknown")
            part_num = part.get("part_number", 1)
            total    = part.get("total_parts", 1)
            suffix   = f"_pt{part_num}of{total}" if total > 1 else ""
            out_path = Path(audio_dir) / language / f"{story_id}{suffix}.mp3"
            if self.generate(
                part.get("full_script", ""),
                language,
                out_path,
                narrator_gender=part.get("narrator_gender", "female"),
            ):
                part["audio_path"] = str(out_path)
                generated.append(out_path)
            else:
                logger.error("Falha no audio: %s (%s)", story_id, language)
        return generated