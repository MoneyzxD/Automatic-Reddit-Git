"""
metadata.py
===========
Gera metadados completos para YouTube e TikTok.

Responsabilidades:
    - Descrição personalizada por vídeo via Groq (fallback: templates)
    - Rotação de hashtags via pool em publishing.yaml
    - CTA fixo por idioma via publishing.yaml
    - Blocos youtube{} e tiktok{} prontos para o uploader

Estrutura da descrição:
    1. Resumo curto do conflito (gerado por LLM)
    2. Gancho/pergunta para engajamento (gerado por LLM)
    3. CTA fixo do canal (publishing.yaml)
    4. Hashtags

Providers:
    1. Groq API  — descrição personalizada
    2. Templates — fallback sem LLM

Integração com stages/validator.py:
    Depois que validate_and_fix_metadata() corrige a description e/ou as
    hashtags, chame rebuild_after_validation() ANTES de save() — sem isso
    a correção fica presa nos campos soltos do dict e nunca chega nos
    blocos youtube{}/tiktok{} que realmente vão pro uploader.
"""
from __future__ import annotations

import json
import logging
import os
import random
from pathlib import Path

logger = logging.getLogger(__name__)

_PUBLISHING_YAML_PATHS = [
    Path("config/publishing.yaml"),
    Path("../config/publishing.yaml"),
    Path(__file__).parent.parent / "config" / "publishing.yaml",
]

_YOUTUBE_CATEGORY_ID = "22"

# ── PROMPTS DE DESCRIÇÃO ──────────────────────────────────────────────────────

DESCRIPTION_PROMPTS = {
    "pt": (
        "Você é especialista em descrições para YouTube Shorts de histórias do Reddit.\n\n"
        "TÍTULO DO VÍDEO: {title}\n"
        "RESUMO DA HISTÓRIA: {story_summary}\n"
        "GÊNERO DO NARRADOR: {narrator_gender}\n\n"
        "TAREFA:\n"
        "Escreva uma descrição curta para YouTube com EXATAMENTE 2 linhas:\n\n"
        "LINHA 1: Uma frase direta resumindo o conflito central da história.\n"
        "LINHA 2: Uma pergunta curta e direta para o espectador comentar.\n\n"
        "REGRAS:\n"
        "- Use concordância de gênero correta para o narrador\n"
        "- Se GÊNERO DO NARRADOR for 'feminino': use 'errada', 'culpada', 'sozinha'\n"
        "- Se GÊNERO DO NARRADOR for 'masculino': use 'errado', 'culpado', 'sozinho'\n"
        "- Linguagem simples e direta — sem floreios\n"
        "- Sem hashtags, sem aspas, sem numeração\n"
        "- Comece a LINHA 1 diretamente com o fato — sem prefixos como "
        "'Meu exame de consciência:', 'Neste vídeo:', 'Uma reflexão:', etc.\n"
        "- Retorne APENAS as 2 linhas. Nada mais.\n\n"
        "EXEMPLOS CORRETOS:\n"
        "Recusei emprestar dinheiro pra minha irmã depois que ela me humilhou na frente de todos.\n"
        "Você teria feito o mesmo?\n\n"
        "Meu primo trouxe a namorada pro jantar e virou um desastre em 5 minutos.\n"
        "O que você teria feito no lugar da minha avó?\n\n"
        "Expulsei meu irmão de casa depois de descobrir o que ele estava fazendo.\n"
        "Você estaria do meu lado?\n\n"
        "EXEMPLOS INCORRETOS — nunca faça isso:\n"
        "Meu exame de consciência: Será que foi errada em...\n"
        "Uma reflexão sobre limites: Decidi que...\n"
        "Neste vídeo: A história de...\n"
        "Hoje quero contar sobre...\n"
    ),
    "en": (
        "You are a specialist in YouTube Shorts descriptions for Reddit stories.\n\n"
        "VIDEO TITLE: {title}\n"
        "STORY SUMMARY: {story_summary}\n"
        "NARRATOR GENDER: {narrator_gender}\n\n"
        "TASK:\n"
        "Write a short YouTube description with EXACTLY 2 lines:\n\n"
        "LINE 1: A direct sentence summarizing the central conflict.\n"
        "LINE 2: A short direct question for the viewer to comment on.\n\n"
        "RULES:\n"
        "- Use correct gender agreement for the narrator\n"
        "- Simple and direct language — no fluff\n"
        "- No hashtags, no quotes, no numbering\n"
        "- Start LINE 1 directly with the fact — no prefixes like "
        "'My reflection:', 'In this video:', 'A look at:', etc.\n"
        "- Return ONLY the 2 lines. Nothing else.\n\n"
        "CORRECT EXAMPLES:\n"
        "I refused to lend money to my sister after she humiliated me in front of everyone.\n"
        "Would you have done the same?\n\n"
        "My cousin brought his girlfriend to dinner and it turned into a disaster in 5 minutes.\n"
        "What would you have done in my grandmother's place?\n\n"
        "I kicked my brother out after finding out what he was doing.\n"
        "Would you be on my side?\n\n"
        "INCORRECT EXAMPLES — never do this:\n"
        "My reflection: Was I wrong to...\n"
        "In this video: The story of...\n"
        "A look at boundaries: I decided...\n"
        "Today I want to share...\n"
    ),
    "es": (
        "Eres especialista en descripciones para YouTube Shorts de historias de Reddit.\n\n"
        "TÍTULO DEL VIDEO: {title}\n"
        "RESUMEN DE LA HISTORIA: {story_summary}\n"
        "GÉNERO DEL NARRADOR: {narrator_gender}\n\n"
        "TAREA:\n"
        "Escribe una descripción corta para YouTube con EXACTAMENTE 2 líneas:\n\n"
        "LÍNEA 1: Una frase directa resumiendo el conflicto central.\n"
        "LÍNEA 2: Una pregunta corta y directa para que el espectador comente.\n\n"
        "REGLAS:\n"
        "- Usa concordancia de género correcta para el narrador\n"
        "- Si GÉNERO DEL NARRADOR es 'femenino': usa 'equivocada', 'culpable', 'sola'\n"
        "- Si GÉNERO DEL NARRADOR es 'masculino': usa 'equivocado', 'culpable', 'solo'\n"
        "- Lenguaje simple y directo — sin adornos\n"
        "- Sin hashtags, sin comillas, sin numeración\n"
        "- Comienza la LÍNEA 1 directamente con el hecho — sin prefijos como "
        "'Mi reflexión:', 'En este video:', 'Una mirada a:', etc.\n"
        "- Devuelve SOLO las 2 líneas. Nada más.\n\n"
        "EJEMPLOS CORRECTOS:\n"
        "Me negué a prestarle dinero a mi hermana después de que me humilló delante de todos.\n"
        "¿Habrías hecho lo mismo?\n\n"
        "Mi primo trajo a su novia a la cena y se convirtió en un desastre en 5 minutos.\n"
        "¿Qué habrías hecho en el lugar de mi abuela?\n\n"
        "Eché a mi hermano de casa después de descubrir lo que estaba haciendo.\n"
        "¿Estarías de mi lado?\n\n"
        "EJEMPLOS INCORRECTOS — nunca hagas esto:\n"
        "Mi reflexión: ¿Estuve mal en...\n"
        "En este video: La historia de...\n"
        "Una mirada a los límites: Decidí...\n"
        "Hoy quiero contar sobre...\n"
    ),
}

DESCRIPTION_SYSTEM_PROMPTS = {
    "pt": (
        "Você escreve descrições para YouTube Shorts. "
        "Retorne APENAS 2 linhas conforme solicitado. "
        "Sem títulos, sem numeração, sem explicações. "
        "RESPONDA SEMPRE EM PORTUGUÊS DO BRASIL."
    ),
    "en": (
        "You write descriptions for YouTube Shorts. "
        "Return ONLY 2 lines as requested. "
        "No titles, no numbering, no explanations. "
        "ALWAYS RESPOND IN ENGLISH."
    ),
    "es": (
        "Escribes descripciones para YouTube Shorts. "
        "Devuelve SOLO 2 líneas según lo solicitado. "
        "Sin títulos, sin numeración, sin explicaciones. "
        "RESPONDE SIEMPRE EN ESPAÑOL."
    ),
}

# ── TEMPLATES FALLBACK ────────────────────────────────────────────────────────

DESCRIPTION_TEMPLATES = {
    "pt": [
        "Uma história real sobre limites, família e respeito.\nVocê teria feito o mesmo?",
        "Às vezes a família é quem mais machuca.\nO que você faria no meu lugar?",
        "Tomei uma decisão difícil e agora me pergunto se fiz certo.\nE você, o que acha?",
        "Uma situação que mudou tudo entre mim e minha família.\nVocê estaria do meu lado?",
        "Cheguei no meu limite e tomei uma atitude.\nFiz certo ou errei?",
    ],
    "en": [
        "A real story about boundaries, family and respect.\nWould you have done the same?",
        "Sometimes family hurts the most.\nWhat would you do in my place?",
        "I made a hard decision and now I wonder if I was right.\nWhat do you think?",
        "A situation that changed everything between me and my family.\nWould you be on my side?",
        "I reached my limit and took action.\nWas I right or wrong?",
    ],
    "es": [
        "Una historia real sobre límites, familia y respeto.\n¿Habrías hecho lo mismo?",
        "A veces la familia es quien más duele.\n¿Qué harías en mi lugar?",
        "Tomé una decisión difícil y ahora me pregunto si hice bien.\n¿Y tú qué opinas?",
        "Una situación que cambió todo entre mi familia y yo.\n¿Estarías de mi lado?",
        "Llegué a mi límite y actué.\n¿Hice bien o me equivoqué?",
    ],
}

BASE_TAGS = {
    "pt": ["reddit", "historias reddit", "reddit em portugues", "stories",
           "historia real", "desabafo", "relacionamento", "shorts"],
    "en": ["reddit", "reddit stories", "true stories", "storytime",
           "reddit reading", "aita", "relationship advice", "shorts"],
    "es": ["reddit", "historias reddit", "reddit espanol", "storytime",
           "historia real", "desahogo", "relaciones", "shorts"],
}


# ── CARREGAMENTO DO PUBLISHING.YAML ──────────────────────────────────────────

def _load_publishing_config() -> dict:
    for path in _PUBLISHING_YAML_PATHS:
        if path.exists():
            try:
                import yaml
                with open(path, encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.debug("Erro ao carregar publishing.yaml: %s", e)
            break
    return {}


def _get_channel_cta(language: str) -> str:
    """Retorna CTA fixo do canal por idioma do publishing.yaml."""
    pub = _load_publishing_config()
    cta_map = pub.get("channel_cta", {})
    defaults = {
        "pt": "Inscreva-se no canal e ative o sino para não perder nenhuma história!",
        "en": "Subscribe and hit the bell so you never miss a story!",
        "es": "¡Suscríbete y activa la campana para no perderte ninguna historia!",
    }
    return cta_map.get(language, defaults.get(language, defaults["en"]))


def _pick_hashtags(language: str) -> tuple[list, str]:
    """
    Sorteia hashtags do pool em publishing.yaml.
    Retorna (lista, string_formatada).
    """
    pub      = _load_publishing_config()
    pool_cfg = pub.get("hashtag_pools", {}).get(language, {})

    if not pool_cfg and language == "pt-br":
        pool_cfg = pub.get("hashtag_pools", {}).get("pt", {})

    core     = pool_cfg.get("core", ["#shorts", "#reddit"])
    rotation = pool_cfg.get("rotation", [])
    pick_n   = pool_cfg.get("pick_from_rotation", 4)

    if rotation:
        picked = random.sample(rotation, min(pick_n, len(rotation)))
    else:
        fallback = {
            "pt": ["#historias", "#desabafo", "#familia", "#drama"],
            "en": ["#stories", "#family", "#drama", "#storytime"],
            "es": ["#historias", "#familia", "#drama", "#desahogo"],
        }
        picked = fallback.get(language, fallback["en"])

    all_tags = core + picked
    tags_str = " ".join(all_tags)
    return all_tags, tags_str


# ── GERAÇÃO DE DESCRIÇÃO VIA LLM ─────────────────────────────────────────────

class MetadataGenerator:

    def __init__(self, config: dict):
        self.config       = config
        self.llm_enabled  = config.get("llm_enabled", True)
        self.groq_key     = os.environ.get("GROQ_API_KEY", "") or config.get("groq_api_key", "")
        self.groq_model   = config.get("groq_model", "openai/gpt-oss-20b")
        self.ollama_url   = config.get("ollama_url", "http://localhost:11434/api/generate")
        self.ollama_model = config.get("ollama_model", "llama3.2")

    def _description_via_groq(self, title: str, story_summary: str,
                               language: str, narrator_gender: str) -> str | None:
        if not self.groq_key or not self.llm_enabled:
            return None
        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(self.groq_key, "metadata")

            gender_label = {
                "female":  {"pt": "feminino", "en": "female",   "es": "femenino"},
                "male":    {"pt": "masculino", "en": "male",     "es": "masculino"},
                "unknown": {"pt": "neutro",    "en": "neutral",  "es": "neutro"},
            }
            gender_str = gender_label.get(narrator_gender, gender_label["unknown"]).get(language, "neutral")

            prompt = DESCRIPTION_PROMPTS.get(language, DESCRIPTION_PROMPTS["en"]).format(
                title=title,
                story_summary=story_summary[:300],
                narrator_gender=gender_str,
            )
            system = DESCRIPTION_SYSTEM_PROMPTS.get(language, DESCRIPTION_SYSTEM_PROMPTS["en"])

            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user",   "content": prompt},
                ],
                temperature=0.75,
                max_tokens=120,
            )
            result = resp.choices[0].message.content.strip().strip('"\'')
            if result and len(result) > 10:
                logger.info("Descrição gerada via Groq (%s): %s", language, result[:80])
                return result
        except Exception as e:
            logger.debug("Groq falhou para descrição: %s", e)
        return None

    def _description_via_template(self, language: str) -> str:
        templates = DESCRIPTION_TEMPLATES.get(language, DESCRIPTION_TEMPLATES["en"])
        return random.choice(templates)

    def _build_full_description(self, description_body: str, cta: str,
                                 hashtags_str: str, language: str,
                                 part: int, total: int) -> str:
        """
        Monta descrição completa:
            [resumo + gancho]
            [parte se houver]
            [CTA fixo]
            [hashtags]
        """
        parts = [description_body.strip()]

        if total > 1:
            labels = {
                "pt": f"Parte {part} de {total}",
                "en": f"Part {part} of {total}",
                "es": f"Parte {part} de {total}",
            }
            parts.append(labels.get(language, f"Part {part} of {total}"))

        parts.append(cta)
        parts.append(hashtags_str)

        return "\n\n".join(parts)

    def _build_youtube_block(self, hook: str, full_description: str,
                              hashtags: list, language: str) -> dict:
        yt_title = f"{hook} #shorts"[:100]

        yt_tags = BASE_TAGS.get(language, BASE_TAGS["en"]).copy()
        yt_tags += [h.lstrip("#") for h in hashtags if h.startswith("#")]
        yt_tags = list(dict.fromkeys(yt_tags))[:25]

        return {
            "title":         yt_title,
            "description":   full_description[:5000],
            "tags":          yt_tags,
            "category_id":   _YOUTUBE_CATEGORY_ID,
            "made_for_kids": False,
            "visibility":    "public",
        }

    def _build_tiktok_block(self, hook: str, description_body: str,
                             hashtags: list, hashtags_str: str) -> dict:
        caption = f"{hook} {hashtags_str}"
        if len(caption) > 2200:
            caption = caption[:2197] + "..."

        short_desc = description_body.split("\n")[0][:120]

        return {
            "title":           hook[:150],
            "hashtags":        hashtags,
            "description":     short_desc,
            "caption":         caption,
            "disable_duet":    False,
            "disable_comment": False,
            "visibility":      "PUBLIC_TO_EVERYONE",
        }

    def generate(self, story: dict, language: str,
                 part: int = 1, total: int = 1,
                 hook: str = "", narrator_gender: str = "unknown") -> dict:
        """
        Gera metadados completos para uma parte de história.
        Inclui blocos youtube{} e tiktok{} prontos para o uploader.
        """
        title         = story.get("title", "Untitled")
        story_summary = story.get("text", "")[:300]

        hashtags, hashtags_str = _pick_hashtags(language)
        cta = _get_channel_cta(language)

        # Descrição personalizada
        description_body = self._description_via_groq(
            title, story_summary, language, narrator_gender
        )
        if not description_body:
            from utils import telemetry
            telemetry.record_fallback("metadata", language, "Groq indisponivel — descricao via template")
            description_body = self._description_via_template(language)

        # Descrição completa com CTA e hashtags
        full_description = self._build_full_description(
            description_body, cta, hashtags_str, language, part, total
        )

        # Hook para títulos — usa hook passado ou title como fallback
        hook_for_blocks = hook if hook else title

        youtube = self._build_youtube_block(
            hook_for_blocks, full_description, hashtags, language
        )
        tiktok = self._build_tiktok_block(
            hook_for_blocks, description_body, hashtags, hashtags_str
        )

        return {
            "title":           title,
            "hook":            hook_for_blocks,
            "description":     description_body,
            "full_description": full_description,
            "hashtags":        hashtags,
            "hashtags_string": hashtags_str,
            "youtube":         youtube,
            "tiktok":          tiktok,
            "language":        language,
            "part":            part,
            "total_parts":     total,
            "story_id":        story.get("id", ""),
        }

    def save(self, metadata: dict, output_path: Path) -> None:
        """Salva metadados como JSON."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)
        logger.info("Metadados salvos: %s", output_path.name)

    def rebuild_after_validation(self, metadata: dict, new_description: str,
                                 new_hashtags: list) -> dict:
        """
        Reconstroi full_description e os blocos youtube{}/tiktok{} depois
        que o validador (stages/validator.py) corrige a description ou as
        hashtags. Sem isso, a correcao ficaria presa nos campos soltos do
        dict e nunca chegaria nos blocos que realmente vao pro uploader.

        Chame isso em main.py logo apos validate_and_fix_metadata(),
        ANTES de meta_gen.save().
        """
        language = metadata.get("language", "en")
        part     = metadata.get("part", 1)
        total    = metadata.get("total_parts", 1)
        hook     = metadata.get("hook") or metadata.get("title", "")

        cta          = _get_channel_cta(language)
        hashtags_str = " ".join(new_hashtags)

        full_description = self._build_full_description(
            new_description, cta, hashtags_str, language, part, total,
        )
        youtube = self._build_youtube_block(hook, full_description, new_hashtags, language)
        tiktok  = self._build_tiktok_block(hook, new_description, new_hashtags, hashtags_str)

        metadata["description"]      = new_description
        metadata["hashtags"]         = new_hashtags
        metadata["hashtags_string"]  = hashtags_str
        metadata["full_description"] = full_description
        metadata["youtube"]          = youtube
        metadata["tiktok"]           = tiktok

        logger.info("Metadados reconstruidos apos validacao (%s)", language)
        return metadata