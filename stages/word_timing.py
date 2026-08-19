"""
word_timing.py
==============
Gera audio via edge-tts v7.x e extrai timestamps word-level reais
usando faster-whisper com CUDA.

Arquitetura:
    PRIMARIO:  edge-tts v7.x  -> voz natural PT-BR/ES/EN
    TIMING:    faster-whisper -> timestamps reais por palavra (CUDA)
    FALLBACK1: gTTS           -> se edge-tts falhar
    FALLBACK2: estimativa     -> se whisper tambem falhar

Estilo ASS:
    - Palavra por palavra, centralizada
    - UPPERCASE
    - Fill vermelho brilhante
    - Outline preto grosso (5px)
    - Drop shadow
    - Fonte Impact
    - Animacao bounce: 80% -> 115% -> 100%
"""
from __future__ import annotations

import asyncio
import difflib
import json
import logging
import re
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# ── CONSTANTES DE ESTILO ASS ─────────────────────────────────────────────────
ASS_RED    = "&H000000FF"
ASS_YELLOW = "&H0000FFFF"
ASS_BLACK  = "&H00000000"
ASS_SHADOW = "&H80000000"

ASS_HEADER = (
    "[Script Info]\n"
    "ScriptType: v4.00+\n"
    "PlayResX: 1080\n"
    "PlayResY: 1920\n"
    "ScaledBorderAndShadow: yes\n"
    "YCbCr Matrix: TV.709\n"
    "\n"
    "[V4+ Styles]\n"
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
    "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
    "Alignment, MarginL, MarginR, MarginV, Encoding\n"
    "Style: Word,Impact,96,{red},{yellow},{black},{shadow},"
    "-1,0,0,0,100,100,2,0,1,5,3,5,30,30,120,1\n"
    "\n"
    "[Events]\n"
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
).format(red=ASS_RED, yellow=ASS_YELLOW, black=ASS_BLACK, shadow=ASS_SHADOW)

# Modelo whisper singleton — carregado uma vez por processo
_whisper_model = None


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _seconds_to_ass(t: float) -> str:
    """Converte segundos para formato ASS: H:MM:SS.cc"""
    t  = max(0.0, t)
    h  = int(t // 3600)
    m  = int((t % 3600) // 60)
    s  = int(t % 60)
    cs = int(round((t % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _bounce_tag() -> str:
    """Tag ASS de animacao bounce: 80% -> 115% -> 100%"""
    return r"{\an5\fscx80\fscy80\t(0,250,\fscx115\fscy115)\t(250,400,\fscx100\fscy100)}"


def _count_syllables(word: str) -> int:
    """Estima silabas por contagem de vogais consecutivas."""
    vowels = re.findall(r"[aeiouáéíóúàâêîôûãõ]+", word.lower())
    return max(1, len(vowels))


def _get_audio_duration(audio_path: Path) -> float:
    """Duracao real do audio via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(audio_path),
            ],
            capture_output=True, text=True, timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _distribute_words(words: list, sent_start: float, sent_duration: float) -> list:
    """Distribui timestamps word-level dentro de uma frase por peso de silabas."""
    if not words:
        return []
    sylls  = [_count_syllables(w) for w in words]
    total  = sum(sylls) or len(words)
    cursor = sent_start
    result = []
    for word, s in zip(words, sylls):
        dur = (s / total) * sent_duration
        result.append({
            "word":     word,
            "start":    cursor,
            "duration": max(0.12, dur),
        })
        cursor += dur
    return result


# ── EDGE-TTS: GERACAO DE AUDIO ────────────────────────────────────────────────

async def _generate_audio_edge_tts(
    text: str, voice: str, rate: str, audio_path: Path
) -> bool:
    """
    Gera audio com edge-tts v7.x.
    Retorna True se o audio foi salvo com sucesso.
    """
    try:
        import edge_tts
    except ImportError:
        logger.error("edge-tts nao instalado: pip install edge-tts")
        return False

    audio_chunks = []

    try:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch="+0Hz")
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_chunks.append(chunk["data"])

        if not audio_chunks:
            logger.error("edge-tts nao retornou audio")
            return False

        audio_path.parent.mkdir(parents=True, exist_ok=True)
        with open(audio_path, "wb") as f:
            for chunk in audio_chunks:
                f.write(chunk)

        logger.info("Audio gerado via edge-tts: %s", audio_path.name)
        return True

    except Exception as e:
        logger.error("edge-tts falhou: %s", e)
        return False


def generate_edge_tts_audio(
    text: str, voice: str, rate: str, audio_path: Path
) -> bool:
    """Wrapper sincrono para geracao de audio edge-tts."""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(
            _generate_audio_edge_tts(text, voice, rate, audio_path)
        )
        loop.close()
        return result
    except Exception as e:
        logger.error("Event loop edge-tts falhou: %s", e)
        return False


# ── FASTER-WHISPER: TIMESTAMPS REAIS ─────────────────────────────────────────

def _get_whisper_model():
    """
    Retorna instancia singleton do WhisperModel.
    Usa CUDA se disponivel, CPU como fallback.
    """
    global _whisper_model
    if _whisper_model is not None:
        return _whisper_model

    try:
        from faster_whisper import WhisperModel

        # Tenta CUDA primeiro
        try:
            _whisper_model = WhisperModel(
                "small",
                device="cuda",
                compute_type="float16",
            )
            logger.info("Whisper carregado: device=cuda, compute_type=float16")
        except Exception as e:
            logger.warning("CUDA indisponivel para Whisper (%s) — usando CPU", e)
            _whisper_model = WhisperModel(
                "small",
                device="cpu",
                compute_type="int8",
            )
            logger.info("Whisper carregado: device=cpu, compute_type=int8")

        return _whisper_model

    except ImportError:
        logger.error("faster-whisper nao instalado: pip install faster-whisper")
        return None


def _repair_corrupted_words(word_boundaries: list, reference_text: str) -> list:
    """
    Repara palavras corrompidas na transcricao do faster-whisper.

    O decode por-palavra do whisper as vezes corrompe caracteres acentuados
    (efeito colateral conhecido de decodificar um subconjunto de tokens BPE
    isoladamente, cortando uma sequencia UTF-8 multi-byte no meio) — produz
    o caractere de substituicao U+FFFD ('�') no lugar de uma letra, ou
    ate embaralha um trecho maior da palavra (ex: "verossimil" -> "veroc?nio").

    Como o texto ORIGINAL (mandado pro TTS) e conhecido e correto, qualquer
    palavra transcrita contendo '�' e substituida pela palavra mais
    parecida do texto original — mantendo o timing real do whisper, so
    corrigindo o texto exibido na legenda.
    """
    if not reference_text:
        return word_boundaries

    candidates = re.findall(r"[\wÀ-ÿ]+", reference_text, flags=re.UNICODE)
    if not candidates:
        return word_boundaries

    candidates_lower = [c.lower() for c in candidates]
    repaired = 0

    for wb in word_boundaries:
        word = wb.get("word", "")
        if "�" not in word:
            continue

        skeleton = word.replace("�", "").strip().lower()
        matches = difflib.get_close_matches(skeleton, candidates_lower, n=1, cutoff=0.5)
        if matches:
            idx = candidates_lower.index(matches[0])
            wb["word"] = candidates[idx]
            repaired += 1
        else:
            # Sem candidato parecido o suficiente — pelo menos remove o
            # caractere de substituicao pra nao vazar '�' pra legenda
            wb["word"] = word.replace("�", "")

    if repaired:
        logger.warning(
            "Whisper corrompeu %d palavra(s) com acentos (efeito colateral do decode "
            "por-palavra) — reparadas usando o texto original como referencia",
            repaired,
        )

    return word_boundaries


def extract_word_timestamps_whisper(
    audio_path: Path,
    language: str = "pt",
    reference_text: str = "",
) -> list:
    """
    Extrai timestamps word-level reais do audio via faster-whisper.

    Retorna lista de:
        {"word": str, "start": float, "duration": float}

    language: "pt" | "en" | "es"
    """
    model = _get_whisper_model()
    if model is None:
        return []

    # Mapeia codigos de idioma do pipeline para o formato whisper
    lang_map = {"pt": "pt", "en": "en", "es": "es"}
    whisper_lang = lang_map.get(language, "pt")

    try:
        segments, info = model.transcribe(
            str(audio_path),
            language=whisper_lang,
            word_timestamps=True,
            vad_filter=True,          # remove silencio — melhora precisao
            vad_parameters=dict(
                min_silence_duration_ms=300,
            ),
        )

        word_boundaries = []
        for segment in segments:
            if segment.words is None:
                continue
            for word in segment.words:
                clean = word.word.strip()
                if not clean:
                    continue
                word_boundaries.append({
                    "word":     clean,
                    "start":    float(word.start),
                    "duration": max(0.10, float(word.end) - float(word.start)),
                })

        logger.info(
            "Whisper extraiu %d word timestamps de %s",
            len(word_boundaries), audio_path.name,
        )
        word_boundaries = _repair_corrupted_words(word_boundaries, reference_text)
        return word_boundaries

    except Exception as e:
        logger.error("Whisper falhou em %s: %s", audio_path.name, e)
        return []


# ── PIPELINE PRINCIPAL ────────────────────────────────────────────────────────

def generate_audio_with_timestamps(
    text: str,
    voice: str,
    rate: str,
    audio_path: Path,
    language: str = "pt",
) -> tuple[bool, list]:
    """
    Pipeline completo: gera audio + extrai timestamps word-level reais.

    Fluxo:
        1. edge-tts v7.x  -> gera audio natural
        2. faster-whisper -> timestamps reais por palavra (CUDA)
        3. Se edge-tts falhar -> gTTS como fallback de audio
        4. Se whisper falhar  -> estimativa por silabas

    Retorna: (sucesso_audio: bool, word_boundaries: list)
    """
    audio_ok = generate_edge_tts_audio(text, voice, rate, audio_path)

    # Fallback de audio: gTTS
    if not audio_ok:
        logger.warning("edge-tts falhou — tentando gTTS como fallback")
        audio_ok = _gtts_fallback(text, language, audio_path)

    if not audio_ok:
        logger.error("Geracao de audio falhou completamente")
        return False, []

    # Timestamps reais via Whisper
    boundaries = extract_word_timestamps_whisper(audio_path, language=language, reference_text=text)

    # Fallback de timing: estimativa por silabas
    if not boundaries:
        logger.warning("Whisper nao retornou boundaries — usando estimativa por silabas")
        duration   = _get_audio_duration(audio_path) or (len(text.split()) * 0.35)
        boundaries = estimate_word_timestamps(text, duration)

    return True, boundaries


def _gtts_fallback(text: str, language: str, audio_path: Path) -> bool:
    """Gera audio via gTTS como ultimo recurso."""
    try:
        from gtts import gTTS
        lang_map = {"pt": "pt", "en": "en", "es": "es"}
        tts = gTTS(text=text, lang=lang_map.get(language, "pt"), slow=False)
        audio_path.parent.mkdir(parents=True, exist_ok=True)
        tts.save(str(audio_path))
        logger.info("Audio gerado via gTTS fallback: %s", audio_path.name)
        return True
    except Exception as e:
        logger.error("gTTS fallback falhou: %s", e)
        return False


# ── ESTIMATIVA DE TIMESTAMPS (FALLBACK FINAL) ─────────────────────────────────

def estimate_word_timestamps(text: str, total_duration: float) -> list:
    """
    Estima timestamps por silabas.
    Usado apenas quando audio existe mas Whisper falhou.
    """
    words = text.split()
    if not words:
        return []

    syllable_counts = [_count_syllables(w) for w in words]
    total_syllables = sum(syllable_counts) or len(words)

    boundaries = []
    cursor     = 0.0
    for word, sylls in zip(words, syllable_counts):
        dur = (sylls / total_syllables) * total_duration
        boundaries.append({
            "word":     word,
            "start":    cursor,
            "duration": max(0.15, dur),
        })
        cursor += dur

    return boundaries


# ── GERACAO DE ASS ────────────────────────────────────────────────────────────

def generate_ass(word_boundaries: list, output_path: Path, skip_before: float = 0.0) -> bool:
    """
    Gera arquivo ASS com subtitulos palavra por palavra + animacao bounce.

    skip_before: palavras com start anterior a este valor (segundos) sao
        descartadas — usado pra nao legendar o hook, que ja e mostrado
        por inteiro no card overlay (legendar tambem seria redundante e
        sobreporia visualmente o card).
    """
    if not word_boundaries:
        logger.error("Nenhum word boundary disponivel para gerar ASS")
        return False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    bounce = _bounce_tag()
    lines  = [ASS_HEADER]

    for wb in word_boundaries:
        if float(wb.get("start", 0.0)) < skip_before:
            continue

        word = wb["word"].upper().strip()
        # Remove pontuacao para exibicao limpa
        word = re.sub(r"[^\w\s]", "", word, flags=re.UNICODE).strip()
        if not word:
            continue

        start    = float(wb["start"])
        duration = max(0.20, float(wb["duration"]))
        end      = start + max(duration, 0.35)

        lines.append(
            f"Dialogue: 0,{_seconds_to_ass(start)},{_seconds_to_ass(end)},"
            f"Word,,0,0,0,,{bounce}{word}"
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info("ASS gerado: %s (%d palavras)", output_path.name, len(word_boundaries))
    return True


# ── PERSISTENCIA ──────────────────────────────────────────────────────────────

def save_word_boundaries(boundaries: list, json_path: Path) -> None:
    """Salva word boundaries como JSON para reuso."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(boundaries, f, ensure_ascii=False, indent=2)


def load_word_boundaries(json_path: Path) -> list:
    """Carrega word boundaries de JSON existente."""
    if not json_path.exists():
        return []
    with open(json_path, encoding="utf-8") as f:
        return json.load(f)