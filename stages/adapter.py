
"""
adapter.py
==========
Adapta e limpa o texto bruto do Reddit para narracao.

RESPONSABILIDADE:
    - Limpar usernames e formatacao markdown
    - Entregar texto limpo e fiel em ingles
    - SEM hook de abertura — o hook sera o titulo viral

Providers:
    1. Groq API  — limpeza narrativa de qualidade
    2. Regras    — fallback simples e fiel
"""
from __future__ import annotations

import os
import re
import logging

logger = logging.getLogger(__name__)

ADAPTER_PROMPT_GROQ = """You are a Reddit story cleaning specialist.

Clean and prepare the following Reddit story for narration.

STRICT RULES:
- Preserve ALL facts exactly as written
- DO NOT invent events, characters or details
- DO NOT add a hook or introduction — start naturally from the story
- Remove all Reddit usernames (u/username -> omit completely)
- Remove markdown formatting (**bold**, *italic*, >quotes)
- Remove "Edit:", "Update:", "TLDR:", "TL;DR:" sections
- Replace "OP" with "I" or "the author"
- Keep the story complete — do NOT summarize
- Use natural English narration style
- Do NOT repeat the same transition word twice in a row (e.g. "said said", "told told")
- Return ONLY the cleaned story text, no explanations

Story title: {title}

Story text:
{text}

Cleaned story:"""


class StoryAdapter:

    def __init__(self, config: dict):
        self.config      = config
        self.llm_enabled = config.get("llm_enabled", True)
        self.groq_key    = os.environ.get("GROQ_API_KEY", "") or config.get("groq_api_key", "")
        self.groq_model  = config.get("groq_model", "openai/gpt-oss-20b")

    def _clean_usernames(self, text: str) -> str:
        text = re.sub(r"\bu/[A-Za-z0-9_-]+\b", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\bOP\b",                "I",  text)
        text = re.sub(r"\bthrowaway\w*\b",       "",  text, flags=re.IGNORECASE)
        return text.strip()

    def _clean_reddit_formatting(self, text: str) -> str:
        text = re.sub(r"\*\*(.*?)\*\*",     r"\1",  text)
        text = re.sub(r"\*(.*?)\*",         r"\1",  text)
        text = re.sub(r"&gt;[^\n]*\n",      "",     text)
        text = re.sub(r"\n{3,}",            "\n\n", text)
        text = re.sub(r"Edit\s*\d*\s*:",    "",     text, flags=re.IGNORECASE)
        text = re.sub(r"Update\s*\d*\s*:",  "",     text, flags=re.IGNORECASE)
        text = re.sub(r"TLDR.*",            "",     text, flags=re.IGNORECASE)
        text = re.sub(r"TL;DR.*",           "",     text, flags=re.IGNORECASE)
        return text.strip()

    def _remove_duplicate_words(self, text: str) -> str:
        """Remove palavras de transicao duplicadas consecutivas (disse disse, falou falou)."""
        transition_words = r"(disse|falou|perguntou|respondeu|told|said|asked|replied|dijo|pregunto)"
        text = re.sub(
            r"\b(" + transition_words[1:-1] + r")\b[,.]?\s+\1\b",
            r"\1",
            text,
            flags=re.IGNORECASE,
        )
        return text

    def _build_clean_script(self, story: dict) -> dict:
        """Limpeza basica por regras. Sem hook."""
        text  = story.get("text", "")
        title = story.get("title", "")
        text  = self._clean_reddit_formatting(text)
        text  = self._clean_usernames(text)
        text  = self._remove_duplicate_words(text)
        return {
            "title":       title,
            "hook":        "",
            "body":        text,
            "full_script": text,
            "language":    "en",
            "adapted_by":  "rules",
        }

    def _groq_adapt(self, story: dict) -> dict | None:
        from utils import environment as env
        # Adapter so processa o texto original em ingles (antes da traducao)
        # — usa a chave do "en" pra separar seu consumo do dos outros
        # idiomas, com fallback pra chave generica.
        groq_key = env.groq_api_key("en") or self.groq_key
        if not groq_key:
            logger.debug("Groq ignorado no adapter — GROQ_API_KEY nao definida")
            return None

        title = story.get("title", "")
        text  = story.get("text", "")[:5000]

        try:
            from utils.groq_client import tracked_groq
            client = tracked_groq(groq_key, "adapter")
            prompt = ADAPTER_PROMPT_GROQ.format(title=title, text=text)

            resp = client.chat.completions.create(
                model=self.groq_model,
                messages=[
                    {
                        "role":    "system",
                        "content": (
                            "You are a story cleaning specialist. "
                            "Return ONLY the cleaned story text. "
                            "No introduction, no hook, no explanations."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.3,
                max_tokens=3000,
            )

            result = resp.choices[0].message.content.strip()
            result = re.sub(r"^```[a-z]*\n?", "", result)
            result = re.sub(r"\n?```$",        "", result).strip()
            result = self._remove_duplicate_words(result)

            if result and len(result) > 100:
                logger.info("Script adaptado via Groq")
                return {
                    "title":       title,
                    "hook":        "",
                    "body":        result,
                    "full_script": result,
                    "language":    "en",
                    "adapted_by":  "groq",
                }

        except ImportError:
            logger.debug("groq nao instalado")
        except Exception as e:
            logger.warning("Groq falhou no adapter: %s", e)

        return None

    def adapt(self, story: dict) -> dict:
        """
        Adapta e limpa o script do Reddit.
        Retorna texto em ingles sem hook.
        Ordem: Groq → regras.
        """
        if self.llm_enabled and self.groq_key:
            result = self._groq_adapt(story)
            if result:
                return result

        from utils import telemetry
        telemetry.record_fallback("adapter", "en", "Groq e Ollama indisponiveis")
        logger.info("Script adaptado via regras (fallback)")
        return self._build_clean_script(story)