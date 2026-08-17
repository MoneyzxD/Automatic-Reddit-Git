"""
filter.py
=========
Filtra e pontua histórias extraídas do Reddit.

Score 0-100:
    35 pts -> upvote_ratio
    25 pts -> engajamento (comentários)
    25 pts -> duração ideal (3-7 min a 130 wpm)
    15 pts -> intensidade emocional (VADER)

Dependências gratuitas:
    vaderSentiment   -> pip install vaderSentiment
    better_profanity -> pip install better-profanity
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class StoryFilter:
    """
    Filtra histórias por qualidade, segurança de monetização
    e potencial de engajamento.
    Verifica no banco SQLite se a história já foi processada.
    """

    WORDS_PER_MINUTE = 130

    def __init__(self, config: dict, db=None):
        self.config       = config
        self.db           = db          # PipelineDB — pode ser None
        self.min_score    = config.get("min_score", 65)
        self.blacklist    = [w.lower() for w in config.get("monetization_blacklist", [])]
        self._sentiment   = None
        self._profanity   = None
        self._init_nlp()

    def _init_nlp(self) -> None:
        """Inicializa analisadores de sentimento e profanidade."""
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            self._sentiment = SentimentIntensityAnalyzer()
            logger.info("vaderSentiment carregado")
        except ImportError:
            logger.warning("vaderSentiment não instalado — análise de sentimento desativada")

        try:
            from better_profanity import profanity
            profanity.load_censor_words()
            self._profanity = profanity
            logger.info("better_profanity carregado")
        except ImportError:
            logger.warning("better_profanity não instalado — filtro de profanidade desativado")

    def calculate_score(self, story: dict) -> float:
        """Calcula score de 0 a 100 para uma história."""
        score = 0.0

        # 35 pts — qualidade percebida (upvote ratio)
        ratio  = float(story.get("upvote_ratio", 0))
        score += ratio * 35

        # 25 pts — engajamento (comentários, cap em 500)
        comments = min(int(story.get("num_comments", 0)), 500)
        score   += (comments / 500) * 25

        # 25 pts — duração ideal (3-7 min a 130 wpm)
        words   = int(story.get("word_count", 0))
        minutes = words / self.WORDS_PER_MINUTE
        if 3 <= minutes <= 7:
            score += 25
        elif (2 <= minutes < 3) or (7 < minutes <= 10):
            score += 15
        elif (1 <= minutes < 2) or (10 < minutes <= 20):
            score += 5

        # 15 pts — intensidade emocional (VADER)
        if self._sentiment:
            text      = story.get("text", "")[:3000]
            vs        = self._sentiment.polarity_scores(text)
            intensity = abs(vs.get("compound", 0))
            score    += intensity * 15

        return round(score, 2)

    def is_monetization_safe(self, story: dict) -> bool:
        """Verifica se a história é segura para monetização."""
        text = (story.get("title", "") + " " + story.get("text", "")).lower()
        for word in self.blacklist:
            if word in text:
                logger.debug("Bloqueada por '%s': %s", word, story.get("id"))
                return False
        return True

    def has_acceptable_profanity(self, story: dict) -> bool:
        """Verifica nível de profanidade — retorna True se aceitável."""
        if not self._profanity:
            return True
        text  = story.get("text", "")
        if not text:
            return True
        censored       = self._profanity.censor(text)
        stars          = censored.count("*")
        profanity_ratio = stars / max(len(text), 1)
        threshold      = self.config.get("max_profanity_score", 0.30)
        return profanity_ratio < threshold

    def is_already_processed(self, story_id: str) -> bool:
        """Verifica se história já foi processada (evitar reprocessamento)."""
        if self.db is None:
            return False
        return self.db.story_exists(story_id)

    def filter(self, story: dict) -> tuple:
        """
        Aplica todos os filtros em uma história.
        Retorna: (aprovada: bool, score: float, motivo_rejeicao: str)
        """
        story_id = story.get("id", "")

        # Deduplicação via banco
        if self.is_already_processed(story_id):
            return False, 0.0, "já processada anteriormente"

        # Filtro de upvote ratio mínimo
        min_ratio = float(self.config.get("min_upvote_ratio", 0.80))
        if float(story.get("upvote_ratio", 0)) < min_ratio:
            return False, 0.0, "upvote_ratio baixo"

        # Segurança para monetização
        if not self.is_monetization_safe(story):
            return False, 0.0, "conteúdo não monetizável"

        # Nível de profanidade
        if not self.has_acceptable_profanity(story):
            return False, 0.0, "profanidade acima do limite"

        # Score calculado
        score = self.calculate_score(story)
        if score < self.min_score:
            return False, score, f"score {score} abaixo do mínimo {self.min_score}"

        return True, score, ""

    def run(self, raw_dir: Path) -> list:
        """
        Filtra todas as histórias em raw_dir/*.json.
        Retorna lista de histórias aprovadas, ordenadas por score.
        """
        raw_dir    = Path(raw_dir)
        json_files = sorted(raw_dir.glob("*.json"))
        logger.info(f"Filtrando {len(json_files)} histórias em {raw_dir}")

        approved = []
        rejected = 0

        for path in json_files:
            try:
                with open(path, encoding="utf-8") as f:
                    story = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Erro ao ler {path.name}: {e}")
                continue

            ok, score, reason = self.filter(story)
            story["pipeline_score"]         = score
            story["pipeline_status"]        = "approved" if ok else "rejected"
            story["pipeline_reject_reason"] = reason

            # Atualiza JSON com resultado
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(story, f, ensure_ascii=False, indent=2)
            except OSError as e:
                logger.warning(f"Não foi possível atualizar {path.name}: {e}")

            if ok:
                approved.append(story)
                logger.info(
                    "APROVADA [%3.0f pts] %s — %s",
                    score, story.get("id", ""), story.get("title", "")[:50],
                )
            else:
                rejected += 1
                logger.debug("rejeitada (%s): %s", reason, story.get("id", ""))

        logger.info(
            "Resultado: %d aprovadas / %d rejeitadas (total: %d)",
            len(approved), rejected, len(json_files),
        )
        return sorted(approved, key=lambda x: x["pipeline_score"], reverse=True)
