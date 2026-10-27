"""Confere a coleta real sem salvar histórias nem chamar IA ou YouTube."""
from pathlib import Path
import argparse
import json
import logging
import os
import sys

import yaml

BASE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE_DIR))

from stages.extractor import RedditExtractor


def check_browser(extractor):
    """Sonda Chrome padrão; bloqueio ou desafio termina sem contorno automático."""
    from playwright.sync_api import sync_playwright
    cookies = []
    for part in os.environ.get("REDDIT_SESSION_COOKIE", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name:
            cookies.append({"name": name, "value": value, "domain": ".reddit.com",
                            "path": "/", "secure": True})
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        try:
            context = browser.new_context()
            context.add_cookies(cookies)
            response = context.new_page().goto(
                "https://www.reddit.com/r/AITAH/top.json?t=month&limit=5&raw_json=1",
                wait_until="domcontentloaded", timeout=30000)
            status = response.status if response else None
            posts = response.json().get("data", {}).get("children", []) if status == 200 else []
            usable = sum(bool(extractor.extract_story_text(item.get("data", {})))
                         for item in posts if item.get("kind") == "t3")
            print(json.dumps({"transport": "chrome", "http_status": status,
                              "reddit_posts": len(posts), "reddit_usable": usable,
                              "llm_calls": 0, "youtube_calls": 0}))
            return 0 if usable else 2
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
    config = yaml.safe_load((BASE_DIR / "config/settings.yaml").read_text(encoding="utf-8"))
    extractor = RedditExtractor(config.get("extraction", {}))
    try:
        if args.browser:
            return check_browser(extractor)
        posts = extractor.fetch_subreddit("AITAH", time_filter="month", limit=50)
        usable = sum(bool(extractor.extract_story_text(post)) for post in posts)
        print(json.dumps({"reddit_posts": len(posts), "reddit_usable": usable,
                          "sources": sorted({post.get("source_provider", "reddit") for post in posts}),
                          "llm_calls": 0, "youtube_calls": 0}))
        return 0 if usable else 2
    except Exception as error:
        # Só o tipo: nunca corpo HTTP, cabeçalho de sessão ou conteúdo do post.
        print(json.dumps({"transport": "chrome" if args.browser else "requests",
                          "reddit_error": type(error).__name__, "llm_calls": 0, "youtube_calls": 0}))
        return 2
    finally:
        extractor.session.close()


if __name__ == "__main__":
    raise SystemExit(main())
