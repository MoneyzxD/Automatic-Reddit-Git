"""
extractor.py
============
Extrai histórias reais do Reddit e de seu arquivo público gratuito.

Fontes (em ordem de prioridade):
    1. Reddit JSON autenticado — reddit.com/r/{sub}/top.json
    2. old.reddit.com       — fallback URL alternativa
    3. Arctic Shift        — arquivo público; métricas originais obrigatórias

O cookie fica restrito aos hosts do Reddit; o arquivo não recebe credenciais.
"""
from __future__ import annotations

import json
import time
import random
import logging
import math
import re
from datetime import datetime
from pathlib import Path

import requests

logger = logging.getLogger(__name__)


class RedditExtractor:
    """
    Extrai histórias via sessão Reddit ou arquivo público sem API key.
    """

    REDDIT_URLS = [
        "https://www.reddit.com",
        "https://old.reddit.com",
    ]
    ARCTIC_SHIFT_URL = "https://arctic-shift.photon-reddit.com/api/posts/search"

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

        from utils import environment as env
        cookie = env.reddit_session_cookie()
        if cookie:
            # Trafego de sessao logada continua funcionando mesmo com o
            # Reddit devolvendo 403 pra requisicao anonima (ver
            # utils/environment.py:reddit_session_cookie).
            session.headers["Cookie"] = cookie
            logger.info("Reddit: usando sessao logada (cookie configurado)")

        return session

    # ── FONTE 1: Reddit JSON público ─────────────────────────────────────

    def _fetch_reddit_json(
        self, subreddit: str, time_filter: str = "week", limit: int = 50
    ) -> list:
        """Busca posts via Reddit JSON público (sem API key)."""
        # lstrip() remove QUALQUER caractere do conjunto {r, /}, nao o
        # prefixo "r/" — corrompia nomes como "r/relationship_advice" para
        # "elationship_advice" (o "r" de "relationship" tambem sumia).
        sub = subreddit.removeprefix("r/")

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
                    logger.warning(f"Reddit JSON: resposta OK mas 0 posts para r/{sub} em {base_url}")
                elif resp.status_code == 429:
                    logger.warning(f"Rate limit em r/{sub} — aguardando 60s")
                    time.sleep(60)
                else:
                    # Nivel warning (nao debug): raiz mais provavel de falha
                    # uniforme em todos os subreddits e o Reddit bloqueando o
                    # IP do runner do GitHub Actions (403) — em debug isso
                    # ficava invisivel no log de producao.
                    logger.warning(f"HTTP {resp.status_code} para r/{sub} em {base_url}")
            except requests.RequestException as e:
                logger.warning(f"Erro ao buscar r/{sub} em {base_url}: {e}")

            time.sleep(self.delay + random.uniform(0.5, 1.5))

        return []

    # ── FONTE 2: Arctic Shift (arquivo público gratuito) ─────────────────

    def _fetch_arctic_shift(
        self, subreddit: str, time_filter: str = "month", limit: int = 50
    ) -> list:
        """
        Consulta modesta do arquivo sem transmitir sessão Reddit.
        Espera dois dias para as métricas amadurecerem; não inventa votos/ratio.
        """
        sub = subreddit.removeprefix("r/")
        windows = {"week": "7d", "month": "30d", "year": "365d", "all": None}
        if time_filter not in windows:
            # O arquivo não tem métricas maduras na janela de hora/dia.
            return []
        params = {
            "subreddit": sub,
            "limit": min(max(int(limit), 1), 100),
            "sort": "desc",
            "before": "2d",
        }
        if windows[time_filter]:
            params["after"] = windows[time_filter]
        resp = None
        try:
            resp = requests.get(
                self.ARCTIC_SHIFT_URL, params=params, timeout=30, allow_redirects=False,
                headers={"User-Agent": "RedditStories/1.0"},
            )
            if resp.status_code == 200:
                data = resp.json()
                posts = data.get("data", []) if isinstance(data, dict) else []
                if not isinstance(posts, list):
                    return []
                if posts:
                    normalized = []
                    for p in posts:
                        if not isinstance(p, dict):
                            continue
                        ratio = p.get("upvote_ratio")
                        if (not isinstance(p.get("id"), str)
                                or not re.fullmatch(r"[a-z0-9]{1,16}", p["id"])
                                or not isinstance(p.get("subreddit"), str)
                                or p["subreddit"].casefold() != sub.casefold()
                                or not isinstance(p.get("title"), str)
                                or not isinstance(p.get("selftext"), str)
                                or p.get("removed_by_category")
                                or type(ratio) not in {int, float}
                                or not math.isfinite(ratio) or not 0 <= ratio <= 1
                                or any(type(p.get(key)) is not int or p[key] < 0
                                       for key in ("score", "num_comments"))
                                or not self.extract_story_text(p)):
                            continue
                        normalized.append({
                            "id":           p["id"],
                            "title":        p["title"],
                            "selftext":     p["selftext"],
                            "score":        p["score"],
                            "upvote_ratio": ratio,
                            "num_comments": p["num_comments"],
                            "created_utc":  p.get("created_utc", 0),
                            "permalink":    f"/r/{sub}/comments/{p['id']}/",
                            "subreddit":    sub,
                            "source_provider": "arctic_shift",
                            "source_retrieved_utc": p.get("retrieved_on"),
                        })
                    logger.info("Arctic Shift: %d posts íntegros de r/%s", len(normalized), sub)
                    return normalized
                logger.warning("Arctic Shift: resposta OK mas 0 posts para r/%s", sub)
            else:
                logger.warning("Arctic Shift: HTTP %d para r/%s", resp.status_code, sub)
        except (requests.RequestException, ValueError, TypeError) as error:
            logger.warning("Arctic Shift indisponível para r/%s: %s", sub, type(error).__name__)
        finally:
            if resp is not None:
                resp.close()
        return []

    # ── FETCH COM FALLBACK ────────────────────────────────────────────────

    def fetch_subreddit(
        self, subreddit: str, time_filter: str = "week", limit: int = 50
    ) -> list:
        """
        Busca posts de um subreddit com fallback automático.
        1. Reddit JSON → 2. Arctic Shift
        """
        # Fonte primária: Reddit JSON público
        posts = self._fetch_reddit_json(subreddit, time_filter, limit)
        if posts:
            return posts

        logger.info("Reddit JSON falhou para %s — tentando Arctic Shift", subreddit)
        posts = self._fetch_arctic_shift(subreddit, time_filter, limit)
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
            "subreddit":    subreddit.removeprefix("r/"),
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
        if post.get("source_provider") == "arctic_shift":
            payload["source_provider"] = "arctic_shift"
            payload["source_retrieved_utc"] = post.get("source_retrieved_utc")

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
            logger.info(f"[{i+1}/{len(subreddits)}] Extraindo {sub}")
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
