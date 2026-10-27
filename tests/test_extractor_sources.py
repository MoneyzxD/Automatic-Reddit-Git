"""Regressão do 403 real: arquivo gratuito preserva métricas e não recebe cookie."""
import json

import pytest
import requests

from stages.extractor import RedditExtractor


def post(**changes):
    return dict(id="abc123", title="A family disagreement", selftext="A real source sentence. " * 20,
                subreddit="relationship_advice", score=620, upvote_ratio=0.94, num_comments=510,
                created_utc=1700000000, retrieved_on=1700200000,
                permalink="/r/relationship_advice/comments/abc123/story/", **changes)


class Response:
    def __init__(self, status, data):
        self.status_code, self.data = status, data

    def json(self):
        return self.data

    def close(self):
        pass


def test_403_reddit_usa_arquivo_sem_cookie_e_sem_metricas_inventadas(monkeypatch, tmp_path):
    monkeypatch.setenv("REDDIT_SESSION_COOKIE", "SECRET_CANARY")
    monkeypatch.setattr("stages.extractor.time.sleep", lambda _: None)
    extractor = RedditExtractor({"base_dir": str(tmp_path)})
    monkeypatch.setattr(extractor.session, "get", lambda *a, **k: Response(403, {}))
    calls = []

    def get(url, **options):
        calls.append((url, options))
        return Response(200, {"data": [post()]})

    monkeypatch.setattr(requests, "get", get)
    result = extractor.fetch_subreddit("r/relationship_advice", time_filter="month", limit=50)
    assert len(result) == 1 and result[0]["upvote_ratio"] == 0.94
    assert result[0]["score"] == 620 and result[0]["num_comments"] == 510
    assert calls[0][0] == "https://arctic-shift.photon-reddit.com/api/posts/search"
    assert "SECRET_CANARY" not in json.dumps(calls)
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["params"] == {"subreddit": "relationship_advice", "limit": 50,
                                    "sort": "desc", "before": "2d", "after": "30d"}
    path = extractor.save_raw(result[0], "r/relationship_advice")
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["subreddit"] == "relationship_advice"
    assert saved["source_provider"] == "arctic_shift" and saved["source_retrieved_utc"] == 1700200000


@pytest.mark.parametrize("field,value", [("upvote_ratio", None), ("upvote_ratio", 1.4),
    ("upvote_ratio", float("nan")), ("score", None), ("num_comments", "500"),
    ("id", "../escape"), ("subreddit", "other"), ("selftext", "[removed]"),
    ("removed_by_category", "moderator")])
def test_arquivo_recusa_dado_ausente_corrompido_ou_removido(monkeypatch, tmp_path, field, value):
    extractor = RedditExtractor({"base_dir": str(tmp_path)})
    data = post()
    data[field] = value
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response(200, {"data": [data]}))
    assert extractor._fetch_arctic_shift("relationship_advice", "month", 50) == []


def test_reddit_disponivel_continua_prioritario(monkeypatch, tmp_path):
    extractor = RedditExtractor({"base_dir": str(tmp_path)})
    monkeypatch.setattr(extractor, "_fetch_reddit_json", lambda *a: [post()])
    monkeypatch.setattr(requests, "get", lambda *a, **k: pytest.fail("Arquivo não deveria ser consultado"))
    assert extractor.fetch_subreddit("relationship_advice")[0]["id"] == "abc123"


@pytest.mark.parametrize("status", [403, 429, 503])
def test_arquivo_indisponivel_nao_simula_historia(monkeypatch, tmp_path, status):
    extractor = RedditExtractor({"base_dir": str(tmp_path)})
    monkeypatch.setattr(requests, "get", lambda *a, **k: Response(status, {}))
    assert extractor._fetch_arctic_shift("relationship_advice", "month", 50) == []
