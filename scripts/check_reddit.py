"""Confere a coleta real sem salvar histórias nem chamar IA ou YouTube."""
from pathlib import Path
import json
import logging
import sys

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from stages.extractor import RedditExtractor


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    config = yaml.safe_load((BASE_DIR / "config/settings.yaml").read_text(encoding="utf-8"))
    extractor = RedditExtractor(config.get("extraction", {}))
    try:
        posts = extractor._fetch_reddit_json("AITAH", time_filter="month", limit=5)
        usable = sum(bool(extractor.extract_story_text(post)) for post in posts)
        print(json.dumps({"reddit_posts": len(posts), "reddit_usable": usable,
                          "llm_calls": 0, "youtube_calls": 0}))
        return 0 if usable else 2
    except Exception as error:
        # Só o tipo: nunca corpo HTTP, cabeçalho de sessão ou conteúdo do post.
        print(json.dumps({"reddit_error": type(error).__name__, "llm_calls": 0, "youtube_calls": 0}))
        return 2
    finally:
        extractor.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
