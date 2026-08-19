
"""
gender_detector.py
==================
Detecta e corrige consistencia de genero na narracao.

Duas responsabilidades:
    1. detect()           — detecta genero ANTES da naturalizacao
    2. validate_and_fix() — valida e corrige o texto APOS a naturalizacao,
                            antes do TTS

Providers:
    Groq API  (preferido) — entende semantica, nao usa regex
    Ollama    (fallback)
    Regras    (fallback final — apenas deteccao, sem correcao cega)

PRINCIPIO DE DESIGN:
    Nao usamos listas fixas de substituicao para correcao.
    Substituicao cega por regex nao entende semantica:
        'fiz certo' pode ser 'agi corretamente' (invariavel)
        ou pode ser concordancia errada com o narrador (corrigivel)
    Somente o LLM consegue distinguir os dois casos com seguranca.
    Se LLM indisponivel: texto passa sem alteracao (mais seguro que correcao cega).
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


# ── PROMPTS DE DETECCAO ───────────────────────────────────────────────────────

DETECT_PROMPT_GROQ = {
    "pt": (
        "Analise o texto abaixo e identifique o genero do narrador.\n\n"
        "Retorne APENAS um JSON valido com esta estrutura:\n"
        '{"narrator_gender": "male" ou "female" ou "unknown", '
        '"narrator_confidence": numero entre 0.0 e 1.0, '
        '"corrections_needed": true ou false}\n\n'
        "Pistas de genero em portugues:\n"
        "- '28-year-old woman' ou 'mulher de 28 anos' = feminino\n"
        "- '28-year-old man' ou 'homem de 28 anos' = masculino\n"
        "- 'estava cansada', 'me senti humilhada', 'eu mesma' = feminino\n"
        "- 'estava cansado', 'me senti humilhado', 'eu mesmo' = masculino\n"
        "- 'trabalho de enfermeira' = feminino\n\n"
        "Retorne APENAS o JSON. Nenhum texto adicional.\n\n"
        "Texto:\n"
    ),
    "en": (
        "Analyze the text below and identify the narrator's gender.\n\n"
        "Return ONLY a valid JSON:\n"
        '{"narrator_gender": "male" or "female" or "unknown", '
        '"narrator_confidence": number 0.0-1.0, '
        '"corrections_needed": true or false}\n\n'
        "Gender clues: '28-year-old woman' = female, '28-year-old man' = male.\n\n"
        "Return ONLY the JSON. No additional text.\n\n"
        "Text:\n"
    ),
    "es": (
        "Analiza el texto e identifica el genero del narrador.\n\n"
        "Devuelve SOLO un JSON valido:\n"
        '{"narrator_gender": "male" o "female" o "unknown", '
        '"narrator_confidence": numero 0.0-1.0, '
        '"corrections_needed": true o false}\n\n'
        "Devuelve SOLO el JSON. Sin texto adicional.\n\n"
        "Texto:\n"
    ),
}

# ── PROMPTS DE CORRECAO ───────────────────────────────────────────────────────
# Instrui o LLM a corrigir com entendimento semantico:
# - Estados emocionais do narrador: corrigir
# - Expressoes semanticas proprias ('fiz certo' = 'agi corretamente'): NAO corrigir

CORRECT_PROMPT_GROQ = {
    "pt": (
        "Voce e um editor especialista em concordancia de genero em portugues.\n\n"
        "O NARRADOR deste texto e do genero: {gender_label}\n\n"
        "Corrija APENAS as palavras que expressam ESTADO ou SENTIMENTO do narrador "
        "com concordancia de genero errada.\n\n"
        "CASOS COMUNS QUE DEVEM SER CORRIGIDOS:\n"
        "- Estados emocionais do narrador: culpado/a, humilhado/a, chateado/a, envergonhado/a\n"
        "- Estados fisicos: sozinho/a, perdido/a, confuso/a, cansado/a, traido/a\n"
        "- Identidade: eu mesmo/a, o unico/a, a unica\n"
        "- Julgamentos sobre si: sendo mesquinho/a, sendo cruel, sendo ingrato/a\n"
        "- Frases onde outro personagem descreve o narrador:\n"
        "  Ex: 'meu pai disse que eu estava certo' → 'certa' se narradora for mulher\n"
        "  Ex: 'ela achou que eu era cruel' → manter 'cruel' (invariavel)\n"
        "  Ex: 'ele falou que eu estava errado' → 'errada' se narradora for mulher\n\n"
        "REGRA CRITICA — expressoes semanticas que NAO devem ser corrigidas:\n"
        "  'fiz certo'    = 'agi corretamente'     — NAO corrigir\n"
        "  'foi certo'    = 'foi a decisao certa'  — NAO corrigir\n"
        "  'era correto'  = 'era o certo a fazer'  — NAO corrigir\n\n"
        "IMPORTANTE:\n"
        "- Corrija APENAS palavras que se referem ao NARRADOR\n"
        "- Mantenha o genero dos outros personagens inalterado\n"
        "- Preserve todo o conteudo, emocao e ritmo narrativo\n"
        "- Retorne APENAS o texto corrigido, sem explicacoes\n\n"
        "Texto:\n"
    ),
    "en": (
        "You are a gender consistency editor for English narration.\n\n"
        "The NARRATOR of this text is: {gender_label}\n\n"
        "Fix ONLY emotional or state words referring to the NARRATOR with wrong gender.\n\n"
        "CRITICAL RULE — distinguish before correcting:\n"
        "Some expressions must NOT be changed because they carry semantic meaning:\n"
        "  'I did right'    = 'I made the right decision' — do NOT change\n"
        "  'I was right'    = 'I was correct'             — do NOT change\n"
        "  'that was right' = 'that was the correct move' — do NOT change\n\n"
        "Words to fix when referring to the narrator:\n"
        "  emotional states: guilty, humiliated, upset, ashamed, embarrassed\n"
        "  physical states: alone, lost, confused, tired, betrayed\n"
        "  identity: myself, the only one\n\n"
        "Keep other characters' genders unchanged.\n"
        "Return ONLY the corrected text, no explanations.\n\n"
        "Text:\n"
    ),
    "es": (
        "Eres un editor de concordancia de genero en espanol.\n\n"
        "El NARRADOR de este texto es de genero: {gender_label}\n\n"
        "Corrige SOLO las palabras de estado o sentimiento del NARRADOR con genero incorrecto.\n\n"
        "REGLA CRITICA — distingue antes de corregir:\n"
        "Algunas expresiones NO deben cambiarse porque tienen sentido semantico propio:\n"
        "  'lo hice bien'       = 'tome la decision correcta' — NO cambiar\n"
        "  'estaba en lo cierto' = 'tenia razon'              — NO cambiar\n\n"
        "Palabras a corregir cuando se refieren al narrador:\n"
        "  estados emocionales: culpable, humillado/a, avergonzado/a, confundido/a\n"
        "  estados fisicos: solo/a, perdido/a, cansado/a, traicionado/a\n"
        "  identidad: yo mismo/a, el unico/la unica\n\n"
        "Mantén el genero de los OTROS PERSONAJES igual.\n"
        "Devuelve SOLO el texto corregido, sin explicaciones.\n\n"
        "Texto:\n"
    ),
}

CORRECT_PROMPT_OLLAMA = {
    "pt": (
        "O narrador deste texto e {gender_label}.\n"
        "Corrija apenas palavras de estado emocional do narrador com genero errado.\n"
        "IMPORTANTE: Nao corrija 'fiz certo', 'estava certo', 'era correto' — "
        "essas expressoes significam 'agi corretamente' e nao sao erros de genero.\n"
        "Nao mude o genero dos outros personagens.\n"
        "Retorne apenas o texto corrigido.\n\n"
        "Texto:\n"
    ),
    "en": (
        "The narrator is {gender_label}.\n"
        "Fix emotional/state gender agreement words for the narrator only.\n"
        "IMPORTANT: Do not change 'I did right', 'I was right' — "
        "these mean 'I made the correct decision' and are not gender errors.\n"
        "Return only the corrected text.\n\n"
        "Text:\n"
    ),
    "es": (
        "El narrador es {gender_label}.\n"
        "Corrige solo palabras de estado emocional del narrador con genero incorrecto.\n"
        "IMPORTANTE: No cambies 'lo hice bien', 'estaba en lo cierto' — "
        "son expresiones semanticas, no errores de genero.\n"
        "Devuelve solo el texto corregido.\n\n"
        "Texto:\n"
    ),
}

GENDER_LABELS = {
    "pt": {"female": "feminino (mulher)", "male": "masculino (homem)"},
    "en": {"female": "female (woman)",    "male": "male (man)"},
    "es": {"female": "femenino (mujer)",  "male": "masculino (hombre)"},
}

# ── SINAIS DE DETECCAO (apenas para fallback sem LLM) ────────────────────────

_FEMALE_SIGNALS = [
    r"\b\d+-year-old woman\b", r"\bmulher de \d+ anos\b", r"\(f\)",
    r"\bmy husband\b", r"\bmeu marido\b", r"\bnamorado\b", r"\bboyfriend\b",
    r"\bhumilhada\b", r"\bcansada\b", r"\bchateada\b", r"\benvergonhada\b",
    r"\bsozinha\b", r"\bculpada\b", r"\beu mesma\b", r"\benfermeira\b",
    r"\bmesquinha\b", r"\bconfusa\b", r"\bperdida\b",
]
_MALE_SIGNALS = [
    r"\b\d+-year-old man\b", r"\bhomem de \d+ anos\b", r"\(m\)",
    r"\bmy wife\b", r"\bminha esposa\b", r"\bnamorada\b", r"\bgirlfriend\b",
    r"\bhumilhado\b", r"\bcansado\b", r"\bchateado\b", r"\benvergonhado\b",
    r"\bsozinho\b", r"\bculpado\b", r"\beu mesmo\b", r"\benfermeiro\b",
    r"\bmesquinho\b", r"\bconfuso\b", r"\bperdido\b",
]

# Sinais de POSSIVEL erro — usados apenas para decidir se chama o LLM
# NAO sao usados para substituicao direta
_ERROR_SIGNALS_FEMALE = [
    r"\bme senti culpado\b", r"\bfiquei culpado\b", r"\bme sinto culpado\b",
    r"\bme senti humilhado\b", r"\bfiquei humilhado\b",
    r"\bfiquei sozinho\b", r"\bestava sozinho\b",
    r"\bme senti chateado\b", r"\bfiquei chateado\b",
    r"\bme senti envergonhado\b", r"\bfiquei envergonhado\b",
    r"\bme senti perdido\b", r"\bfiquei perdido\b",
    r"\bme senti confuso\b", r"\bfiquei confuso\b",
    r"\bme senti traido\b", r"\bfiquei traido\b",
    r"\bsendo mesquinho\b", r"\bera mesquinho\b", r"\bsou mesquinho\b",
    r"\beu mesmo\b",
]
_ERROR_SIGNALS_MALE = [
    r"\bme senti culpada\b", r"\bfiquei culpada\b", r"\bme sinto culpada\b",
    r"\bme senti humilhada\b", r"\bfiquei humilhada\b",
    r"\bfiquei sozinha\b", r"\bestava sozinha\b",
    r"\bme senti chateada\b", r"\bfiquei chateada\b",
    r"\bme senti envergonhada\b", r"\bfiquei envergonhada\b",
    r"\bme senti perdida\b", r"\bfiquei perdida\b",
    r"\bme senti confusa\b", r"\bfiquei confusa\b",
    r"\bme senti traida\b", r"\bfiquei traida\b",
    r"\bsendo mesquinha\b", r"\bera mesquinha\b", r"\bsou mesquinha\b",
    r"\beu mesma\b",
]


def _detect_gender_by_rules(text: str) -> tuple[str, float]:
    text_lower   = text.lower()
    female_count = sum(1 for p in _FEMALE_SIGNALS if re.search(p, text_lower))
    male_count   = sum(1 for p in _MALE_SIGNALS   if re.search(p, text_lower))
    if female_count == 0 and male_count == 0:
        return "unknown", 0.5
    if female_count > male_count:
        return "female", min(0.95, 0.6 + female_count * 0.08)
    if male_count > female_count:
        return "male",   min(0.95, 0.6 + male_count * 0.08)
    return "unknown", 0.5


def _has_gender_error_signals(text: str, gender: str) -> bool:
    """
    Detecta sinais de possivel erro para decidir se chama o LLM.
    NAO faz substituicao — apenas sinaliza necessidade de revisao.
    """
    text_lower = text.lower()
    signals    = _ERROR_SIGNALS_FEMALE if gender == "female" else _ERROR_SIGNALS_MALE
    return any(re.search(p, text_lower) for p in signals)


class GenderDetector:

    CONFIDENCE_THRESHOLD = 0.70

    def __init__(self, config: dict = None):
        self.config       = config or {}
        self.groq_key     = os.environ.get("GROQ_API_KEY", "") or self.config.get("groq_api_key", "")
        self.groq_model   = self.config.get("groq_model", "openai/gpt-oss-20b")
        self.ollama_url   = self.config.get("ollama_url", "http://localhost:11434/api/generate")
        self.ollama_model = self.config.get("ollama_model", "llama3.2")
        self.enabled      = self.config.get("enabled", True)

    def _detect_via_groq(self, text: str, language: str) -> dict | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "gender_detector")
            prompt = DETECT_PROMPT_GROQ.get(language, DETECT_PROMPT_GROQ["en"])
            resp   = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": "Return ONLY valid JSON. No additional text."},
                    {"role": "user",   "content": prompt + text[:3000]},
                ],
                temperature=0.1,
                max_tokens=128,
            )
            raw   = resp.choices[0].message.content.strip()
            start = raw.find("{")
            end   = raw.rfind("}") + 1
            if start >= 0 and end > start:
                data = json.loads(raw[start:end])
                logger.info(
                    "Genero detectado via Groq: narrador=%s (confianca=%.2f)",
                    data.get("narrator_gender", "?"),
                    data.get("narrator_confidence", 0),
                )
                return data
        except Exception as e:
            logger.debug("Groq falhou em gender detect: %s", e)
        return None

    def detect(self, text: str, language: str) -> dict:
        result = self._detect_via_groq(text, language)
        if result:
            return result
        from utils import telemetry
        telemetry.record_fallback("gender_detector", language, "Groq indisponivel — deteccao por regras")
        gender, confidence = _detect_gender_by_rules(text)
        logger.info("Genero detectado via regras: narrador=%s (confianca=%.2f)",
                    gender, confidence)
        return {
            "narrator_gender":     gender,
            "narrator_confidence": confidence,
            "corrections_needed":  False,
        }

    def _correct_via_groq(self, text: str, gender: str, language: str) -> str | None:
        from utils import environment as env
        groq_key = env.groq_api_key(language) or self.groq_key
        if not groq_key:
            return None
        try:
            from utils.groq_client import tracked_groq
            client       = tracked_groq(groq_key, "gender_detector")
            labels       = GENDER_LABELS.get(language, GENDER_LABELS["en"])
            gender_label = labels.get(gender, gender)
            prompt       = CORRECT_PROMPT_GROQ.get(language, CORRECT_PROMPT_GROQ["en"])
            prompt       = prompt.format(gender_label=gender_label)
            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": "Return ONLY the corrected text. No explanations."},
                    {"role": "user",   "content": prompt + text},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            result = resp.choices[0].message.content.strip()
            if result:
                logger.info("Correcao de genero via Groq (%s -> %s)", language, gender)
                return result
        except Exception as e:
            logger.debug("Groq falhou em gender correct: %s", e)
        return None

    def _correct_via_ollama(self, text: str, gender: str, language: str) -> str | None:
        try:
            import requests
            labels       = GENDER_LABELS.get(language, GENDER_LABELS["en"])
            gender_label = labels.get(gender, gender)
            prompt       = CORRECT_PROMPT_OLLAMA.get(language, CORRECT_PROMPT_OLLAMA["en"])
            prompt       = prompt.format(gender_label=gender_label) + text
            resp = requests.post(
                self.ollama_url,
                json={"model": self.ollama_model, "prompt": prompt, "stream": False},
                timeout=120,
            )
            if resp.status_code == 200:
                result = resp.json().get("response", "").strip()
                if result and len(result) > 50:
                    logger.info("Correcao de genero via Ollama (%s -> %s)", language, gender)
                    return result
        except Exception as e:
            logger.debug("Ollama falhou em gender correct: %s", e)
        return None

    def validate_and_fix(self, text: str, narrator_gender: str, language: str) -> str:
        """
        Valida e corrige concordancia de genero ANTES do TTS.

        Estrategia escalavel:
        1. PT: detecta sinais de possivel erro por regex (rapido, sem custo de LLM)
           EN/ES: sempre passa pelo LLM (deteccao por regex menos confiavel)
        2. Se ha sinais -> Groq corrige com entendimento semantico completo
        3. Fallback: Ollama com mesmo criterio semantico
        4. Se nenhum LLM disponivel -> texto passa SEM alteracao
           (mais seguro que correcao cega por regex)
        """
        if not self.enabled or narrator_gender == "unknown":
            return text

        # if language == "pt":
        #     has_signals = _has_gender_error_signals(text, narrator_gender)
        #     if not has_signals:
        #         logger.info("Validacao de genero OK — narrador=%s, sem sinais de erro",
        #                     narrator_gender)
        #         return text
        #     logger.info("Sinais de possivel erro de genero — enviando para LLM (narrador=%s)",
        #                 narrator_gender)
        # else:
        #     logger.info("Validacao de genero (%s) — enviando para LLM (narrador=%s)",
        #                 language, narrator_gender)
        
        # Sempre passa pelo LLM — regex nao consegue capturar todos os casos
        # Ex: "meu pai disse que eu estava certo" — erro semântico que regex nao pega
        logger.info("Validacao de genero (%s) — enviando para LLM (narrador=%s)",
                    language, narrator_gender)

        result = self._correct_via_groq(text, narrator_gender, language)
        if result:
            return result

        result = self._correct_via_ollama(text, narrator_gender, language)
        if result:
            return result

        logger.warning("LLM indisponivel para correcao de genero — texto mantido sem alteracao")
        return text

    def apply_consistency(self, text: str, language: str) -> str:
        """Interface legada para compatibilidade."""
        if not self.enabled:
            return text
        gender_info     = self.detect(text, language)
        narrator_gender = gender_info.get("narrator_gender", "unknown")
        confidence      = gender_info.get("narrator_confidence", 1.0)
        if confidence < self.CONFIDENCE_THRESHOLD or narrator_gender == "unknown":
            return text
        return self.validate_and_fix(text, narrator_gender, language)





