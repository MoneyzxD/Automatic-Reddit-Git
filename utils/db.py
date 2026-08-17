"""
utils/db.py
===========
Wrapper SQLite para rastreamento do estado do pipeline.
Evita reprocessar histórias já concluídas.
"""
from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    id              TEXT PRIMARY KEY,
    subreddit       TEXT,
    title           TEXT,
    score           REAL,
    status          TEXT DEFAULT 'extracted',
    extracted_at    TEXT,
    processed_at    TEXT,
    word_count      INTEGER,
    estimated_min   REAL
);

CREATE TABLE IF NOT EXISTS pipeline_parts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    story_id        TEXT,
    language        TEXT,
    part_number     INTEGER,
    total_parts     INTEGER,
    status          TEXT DEFAULT 'pending',
    audio_path      TEXT,
    subtitle_path   TEXT,
    video_path      TEXT,
    thumbnail_path  TEXT,
    metadata_path   TEXT,
    export_path     TEXT,
    created_at      TEXT,
    updated_at      TEXT,
    UNIQUE(story_id, language, part_number)
);

CREATE INDEX IF NOT EXISTS idx_parts_status ON pipeline_parts(status);
CREATE INDEX IF NOT EXISTS idx_stories_status ON stories(status);
"""


class PipelineDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
        logger.info(f"DB inicializado: {self.db_path}")

    def story_exists(self, story_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT id FROM stories WHERE id = ?", (story_id,)
            ).fetchone()
        return row is not None

    def insert_story(self, story: dict) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR IGNORE INTO stories "
                "(id, subreddit, title, score, status, extracted_at, word_count) "
                "VALUES (?, ?, ?, ?, 'extracted', ?, ?)",
                (story["id"], story.get("subreddit", ""),
                 story.get("title", ""), story.get("pipeline_score", 0),
                 datetime.utcnow().isoformat(), story.get("word_count", 0)),
            )

    def update_status(self, story_id: str, language: str, part: int,
                       status: str, **kwargs) -> None:
        now = datetime.utcnow().isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO pipeline_parts "
                "(story_id, language, part_number, total_parts, status, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(story_id, language, part_number) DO UPDATE SET "
                "status=excluded.status, updated_at=excluded.updated_at",
                (story_id, language, part,
                 kwargs.get("total_parts", 1), status, now, now),
            )

    def get_pending(self, language: str | None = None) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM pipeline_parts WHERE status='exported'"
            if language:
                q += f" AND language='{language}'"
            rows = conn.execute(q).fetchall()
        return [dict(r) for r in rows]
