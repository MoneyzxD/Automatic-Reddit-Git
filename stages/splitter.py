"""
splitter.py
===========
Divide historias longas em multiplas partes coerentes (3-7 min).

Calibracao de WPM:
    edge-tts com speech_rate=+8% produz aproximadamente 160-170 wpm
    em portugues brasileiro com voz FranciscaNeural.

    Estimativa conservadora: 155 wpm
    (evita divisoes desnecessarias por superestimacao)

Logica:
    - Estima duracao a 155 wpm
    - Se > 7 min -> divide em partes de ~5.5 min
    - Corta apenas em quebras de paragrafo
    - Partes 2+ repetem o HOOK ORIGINAL no inicio, seguido de "Parte N"
      (sem "de Total" — apenas o numero da parte)
    - A ULTIMA parte (ou a unica parte, se a historia nao for dividida)
      recebe o HOOK DE ENCERRAMENTO (CTA) no final
    - Partes intermediarias mantem o marcador "[Continua na Parte N...]"
"""
import logging

logger = logging.getLogger(__name__)

# WPM calibrado para edge-tts +8% (mais rapido que leitura humana padrao)
# Valor conservador para evitar superestimacao de duracao
WORDS_PER_MINUTE = 155
TARGET_MINUTES   = 5.5
MAX_MINUTES      = 7.0
MIN_MINUTES      = 3.0
TARGET_WORDS     = int(TARGET_MINUTES * WORDS_PER_MINUTE)   # 852
MAX_WORDS        = int(MAX_MINUTES * WORDS_PER_MINUTE)       # 1085
MIN_WORDS        = int(MIN_MINUTES * WORDS_PER_MINUTE)       # 465

# Rótulo de "Parte" usado na repeticao do hook no inicio das partes 2+
PART_LABEL = {
    "pt": "Parte",
    "en": "Part",
    "es": "Parte",
}

# Marcador de continuidade — usado apenas em partes que NAO sao a ultima
CONTINUITY_MARKERS = {
    "pt": {
        "end": "\n\n[Continua na Parte {next} de {total}...]",
    },
    "en": {
        "end": "\n\n[Continued in Part {next} of {total}...]",
    },
    "es": {
        "end": "\n\n[Continua en la Parte {next} de {total}...]",
    },
}


def estimate_duration(text: str, wpm: int = WORDS_PER_MINUTE) -> float:
    """Estima duracao em minutos."""
    return len(text.split()) / wpm


def split_script(
    script_text: str,
    language: str = "pt",
    hook_text: str = "",
    closing_hook_text: str = "",
) -> list:
    """
    Divide um script em partes de 3-7 minutos.

    Parametros:
        script_text       : texto completo do script (ja com hook injetado na parte 1
                             pelo main.py via inject_title_as_hook)
        language           : idioma (pt / en / es)
        hook_text          : hook original — repetido no INICIO das partes 2+
        closing_hook_text  : hook de encerramento (CTA) — injetado no FINAL da
                             ULTIMA parte (ou da unica parte, se nao houver divisao)

    Retorna lista de strings (uma por parte).
    """
    markers   = CONTINUITY_MARKERS.get(language, CONTINUITY_MARKERS["pt"])
    label     = PART_LABEL.get(language, "Parte")
    estimated = estimate_duration(script_text)

    if estimated <= MAX_MINUTES:
        logger.info("Script unico: %.1f min — sem divisao necessaria", estimated)
        single = script_text
        if closing_hook_text:
            single = single + "\n\n" + closing_hook_text
        return [single]

    logger.info("Script longo: %.1f min → iniciando divisao", estimated)

    paragraphs = [p.strip() for p in script_text.split("\n\n") if p.strip()]
    parts      = []
    current    = []
    curr_words = 0

    for para in paragraphs:
        pw = len(para.split())
        if curr_words + pw > MAX_WORDS and current:
            parts.append("\n\n".join(current))
            current    = [para]
            curr_words = pw
        else:
            current.append(para)
            curr_words += pw

    if current:
        parts.append("\n\n".join(current))

    # Mesclar partes muito curtas com a anterior
    merged = []
    buffer = ""
    for part in parts:
        if buffer:
            combined = buffer + "\n\n" + part
            if estimate_duration(combined) <= MAX_MINUTES:
                buffer = combined
                continue
            merged.append(buffer)
            buffer = part
        else:
            buffer = part
    if buffer:
        merged.append(buffer)

    parts = merged
    total = len(parts)

    # Montar cada parte final com os marcadores corretos
    final_parts = []
    for i, part in enumerate(parts):
        current_num = i + 1
        is_first    = (i == 0)
        is_last     = (i == total - 1)

        if is_first:
            # Parte 1 ja contem o hook original (injetado pelo main.py antes do split)
            tagged = part
        else:
            # Partes 2+ repetem o hook original + "Parte N" (sem "de Total")
            if hook_text:
                prefix = f"{hook_text}\n\n{label} {current_num}\n\n"
            else:
                prefix = f"{label} {current_num}\n\n"
            tagged = prefix + part

        if is_last:
            # Ultima parte recebe o hook de encerramento (CTA)
            if closing_hook_text:
                tagged = tagged + "\n\n" + closing_hook_text
        else:
            # Partes intermediarias mantem o marcador de continuidade
            tagged = tagged + markers["end"].format(next=current_num + 1, total=total)

        final_parts.append(tagged)
        dur = estimate_duration(tagged)
        logger.info("  Parte %d/%d: %.1f min", current_num, total, dur)

    return final_parts


def split_story(
    adapted_story: dict,
    language: str = "pt",
    hook_text: str = "",
    closing_hook_text: str = "",
) -> list:
    """
    Recebe script adaptado e retorna lista de partes com metadados.
    Cada parte e um dict com part_number, total_parts, estimated_min.

    Parametros:
        adapted_story      : dict com "full_script" ja contendo o hook injetado
        language            : idioma (pt / en / es)
        hook_text           : hook original — repetido no inicio das partes 2+
        closing_hook_text   : hook de encerramento — injetado na ultima parte
    """
    full_script = adapted_story.get("full_script", "")
    parts_text  = split_script(
        full_script,
        language,
        hook_text=hook_text,
        closing_hook_text=closing_hook_text,
    )
    total = len(parts_text)

    result = []
    for i, part_text in enumerate(parts_text):
        part = adapted_story.copy()
        part["full_script"]   = part_text
        part["part_number"]   = i + 1
        part["total_parts"]   = total
        part["estimated_min"] = round(estimate_duration(part_text), 1)
        result.append(part)

    return result