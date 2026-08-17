"""
extractor.py
============
Extrai histórias do Reddit sem API key.

Fontes (em ordem de prioridade):
    1. Reddit JSON público  — reddit.com/r/{sub}/top.json
    2. old.reddit.com       — fallback URL alternativa
    3. PullPush.io          — substituto comunitário ao Pushshift (gratuito)

Não requer autenticação — apenas User-Agent correto.
"""
from __future__ import annotations

import json
import time
import random
import logging
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class RedditExtractor:
    """
    Extrai histórias do Reddit via JSON público e PullPush.io.
    Sem necessidade de API key ou autenticação.
    """

    REDDIT_URLS = [
        "https://www.reddit.com",
        "https://old.reddit.com",
    ]
    PULLPUSH_URL = "https://api.pullpush.io/reddit/search/submission"

    def __init__(self, config: dict):
        self.config     = config
        self.output_dir = Path(config.get("base_dir", ".")) / "data" / "raw"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.session    = self._build_session()
        self.delay      = float(config.get("request_delay", 2.0))

    def _build_session(self) -> requests.Session:
        """Cria sessão com headers que o Reddit aceita."""
        session = requests.Session()
        session.headers.update({
            "User-Agent": self.config.get(
                "user_agent",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        })
        return session

    # ── FONTE 1: Reddit JSON público ─────────────────────────────────────

    def _fetch_reddit_json(
        self, subreddit: str, time_filter: str = "week", limit: int = 50
    ) -> list:
        """Busca posts via Reddit JSON público (sem API key)."""
        sub = subreddit.lstrip("r/")

        for base_url in self.REDDIT_URLS:
            url    = f"{base_url}/r/{sub}/top.json"
            params = {"t": time_filter, "limit": limit, "raw_json": 1}
            try:
                resp = self.session.get(url, params=params, timeout=15)
                if resp.status_code == 200:
                    data  = resp.json()
                    posts = data.get("data", {}).get("children", [])
                    items = [p["data"] for p in posts if p.get("kind") == "t3"]
                    if items:
                        logger.info(f"Reddit JSON: {len(items)} posts de r/{sub}")
                        return items
                elif resp.status_code == 429:
                    logger.warning(f"Rate limit em r/{sub} — aguardando 60s")
                    time.sleep(60)
                else:
                    logger.debug(f"HTTP {resp.status_code} para r/{sub} em {base_url}")
            except requests.RequestException as e:
                logger.debug(f"Erro ao buscar r/{sub} em {base_url}: {e}")

            time.sleep(self.delay + random.uniform(0.5, 1.5))

        return []

    # ── FONTE 2: PullPush.io (substituto ao Pushshift) ───────────────────

    def _fetch_pullpush(
        self, subreddit: str, limit: int = 25
    ) -> list:
        """
        Busca posts via PullPush.io (gratuito, mantido pela comunidade).
        Endpoint: api.pullpush.io/reddit/search/submission
        """
        sub    = subreddit.lstrip("r/")
        params = {
            "subreddit": sub,
            "sort":      "score",
            "sort_type": "score",
            "size":      limit,
            "score":     ">500",
            "selftext":  "self",  # apenas posts com texto
        }
        try:
            resp = requests.get(
                self.PULLPUSH_URL, params=params, timeout=20,
                headers={"User-Agent": "RedditStories/1.0"},
            )
            if resp.status_code == 200:
                data  = resp.json()
                posts = data.get("data", [])
                if posts:
                    logger.info(f"PullPush: {len(posts)} posts de r/{sub}")
                    # Normalizar para o mesmo formato do Reddit JSON
                    normalized = []
                    for p in posts:
                        normalized.append({
                            "id":           p.get("id", ""),
                            "title":        p.get("title", ""),
                            "selftext":     p.get("selftext", ""),
                            "score":        p.get("score", 0),
                            "upvote_ratio": p.get("upvote_ratio", 0.85),
                            "num_comments": p.get("num_comments", 0),
                            "created_utc":  p.get("created_utc", 0),
                            "permalink":    p.get("permalink", ""),
                            "subreddit":    sub,
                        })
                    return normalized
        except requests.RequestException as e:
            logger.debug(f"PullPush falhou para r/{sub}: {e}")
        return []

    # ── FETCH COM FALLBACK ────────────────────────────────────────────────

    def fetch_subreddit(
        self, subreddit: str, time_filter: str = "week", limit: int = 50
    ) -> list:
        """
        Busca posts de um subreddit com fallback automático.
        1. Reddit JSON → 2. PullPush.io
        """
        # Fonte primária: Reddit JSON público
        posts = self._fetch_reddit_json(subreddit, time_filter, limit)
        if posts:
            return posts

        # Fallback: PullPush.io
        logger.info(f"Reddit JSON falhou para r/{subreddit} — tentando PullPush.io")
        posts = self._fetch_pullpush(subreddit, limit=min(limit, 25))
        return posts

    # ── PROCESSAMENTO ─────────────────────────────────────────────────────

    def extract_story_text(self, post: dict) -> str | None:
        """Extrai e valida o texto da história. Retorna None se inválido."""
        text = post.get("selftext", "").strip()
        if not text or text in ("[deleted]", "[removed]", ""):
            return None
        if len(text) < 200:
            return None
        max_len = int(self.config.get("max_text_length", 15000))
        return text[:max_len]

    def save_raw(self, post: dict, subreddit: str) -> Path | None:
        """Salva o post como JSON para processamento posterior."""
        story_id = post.get("id", "").strip()
        if not story_id:
            return None

        # Evitar sobrescrever posts já extraídos
        out_path = self.output_dir / f"{story_id}.json"
        if out_path.exists():
            logger.debug(f"Post {story_id} já existe — ignorado")
            return None

        text = self.extract_story_text(post)
        if not text:
            return None

        word_count = len(text.split())
        payload = {
            "id":           story_id,
            "subreddit":    subreddit.lstrip("r/"),
            "title":        post.get("title", "").strip(),
            "text":         text,
            "score":        int(post.get("score", 0)),
            "upvote_ratio": float(post.get("upvote_ratio", 0)),
            "num_comments": int(post.get("num_comments", 0)),
            "created_utc":  post.get("created_utc", 0),
            "extracted_at": datetime.utcnow().isoformat(),
            "url":          "https://reddit.com" + post.get("permalink", ""),
            "word_count":   word_count,
        }

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        logger.debug(f"Salvo: {story_id} ({word_count} palavras)")
        return out_path

    def run(self, subreddits: list) -> list:
        """
        Executa extração em batch para lista de subreddits.
        Retorna lista de paths dos JSONs salvos.
        """
        saved_paths  = []
        time_filter  = self.config.get("time_filter", "week")
        limit        = int(self.config.get("posts_per_subreddit", 50))
        min_upvotes  = int(self.config.get("min_upvotes", 50))

        for i, sub in enumerate(subreddits):
            logger.info(f"[{i+1}/{len(subreddits)}] Extraindo r/{sub}")
            posts = self.fetch_subreddit(sub, time_filter=time_filter, limit=limit)

            for post in posts:
                # Filtro rápido de upvotes antes de salvar
                if int(post.get("score", 0)) < min_upvotes:
                    continue
                path = self.save_raw(post, sub)
                if path:
                    saved_paths.append(path)

            # Delay entre subreddits para evitar rate limit
            if i < len(subreddits) - 1:
                sleep_time = self.delay + random.uniform(1.0, 3.0)
                logger.debug(f"Aguardando {sleep_time:.1f}s antes do próximo subreddit")
                time.sleep(sleep_time)

        logger.info(f"Extração concluída: {len(saved_paths)} histórias salvas em {self.output_dir}")
        return saved_paths
