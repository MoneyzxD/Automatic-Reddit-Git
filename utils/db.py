"""
utils/db.py
===========
Wrapper SQLite para rastreamento do estado do pipeline.
Evita reprocessar histórias já concluídas.
"""
from __future__ import annotations

import sqlite3
import logging
import re
from pathlib import Path
from datetime import datetime, timezone

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

CREATE TABLE IF NOT EXISTS story_languages (
    story_id TEXT NOT NULL,
    language TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    profile_id TEXT,
    reason_code TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (story_id, language)
);
"""


def _languages(languages: list[str]) -> list[str]:
    if (not isinstance(languages, list) or not languages
            or any(not isinstance(lang, str) or lang not in {"pt", "pt-br", "en", "es"} for lang in languages)):
        raise ValueError("Idiomas inválidos para recuperação")
    return list(dict.fromkeys("pt" if lang == "pt-br" else lang for lang in languages))


class PipelineDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(SCHEMA)
            if not any(row[1] == "source_sha256" for row in conn.execute("PRAGMA table_info(stories)")):
                conn.execute("ALTER TABLE stories ADD COLUMN source_sha256 TEXT")
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

    def register_story(self, story: dict, languages: list[str], source_hash: str) -> None:
        """Registra a fonte gerenciada sem reabrir ou substituir dedupe legado."""
        languages = _languages(languages)
        if (not isinstance(source_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", source_hash)
                or not isinstance(story.get("id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]+", story["id"])):
            raise ValueError("Fonte inválida para recuperação")
        now = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT source_sha256 FROM stories WHERE id=?", (story["id"],)).fetchone()
            if row is not None and row[0] != source_hash:
                raise ValueError("Fonte legada ou alterada exige reconciliação")
            if row is None:
                conn.execute(
                    "INSERT INTO stories(id,subreddit,title,score,status,extracted_at,word_count,source_sha256) "
                    "VALUES (?,?,?,?,'extracted',?,?,?)",
                    (story["id"], story.get("subreddit", ""), story.get("title", ""),
                     story.get("pipeline_score", 0), now, story.get("word_count", 0), source_hash),
                )
            conn.executemany(
                "INSERT OR IGNORE INTO story_languages(story_id,language,status,updated_at) VALUES (?,?,'pending',?)",
                [(story["id"], language, now) for language in languages],
            )

    def processing_languages(self, story_id: str, languages: list[str]) -> list[str]:
        """Só retoma estados explícitos; existência antiga não prova conclusão."""
        languages = _languages(languages)
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT source_sha256 FROM stories WHERE id=?", (story_id,)).fetchone()
            if row is None:
                return languages
            if row[0] is None:
                return []
            states = dict(conn.execute("SELECT language,status FROM story_languages WHERE story_id=?", (story_id,)))
        return [lang for lang in languages if states.get(lang, "pending") in {"pending", "unavailable"}]

    def recovery_record(self, story_id: str) -> dict | None:
        """Retorna a identidade necessária à retomada; legado não é promovido."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT source_sha256 FROM stories WHERE id=?", (story_id,)).fetchone()
            if row is None or row[0] is None:
                return None
            profiles = {value[0] for value in conn.execute(
                "SELECT profile_id FROM story_languages WHERE story_id=? AND profile_id IS NOT NULL", (story_id,))}
        if len(profiles) > 1:
            raise ValueError("Perfis conflitantes exigem reconciliação")
        return {"source_sha256": row[0], "profile_id": next(iter(profiles), None)}

    def set_language_status(self, story_id: str, language: str, status: str,
                            *, profile_id: str | None = None, reason_code: str = "") -> None:
        """Mantém transições de geração e a identidade única entre idiomas."""
        language = _languages([language])[0]
        transitions = {"pending": {"pending", "processing"}, "unavailable": {"unavailable", "processing"},
                       "processing": {"processing", "exported", "rejected", "unavailable"},
                       "exported": {"exported"}, "rejected": {"rejected"}}
        if (status not in transitions or not isinstance(reason_code, str)
                or (reason_code and not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", reason_code))
                or (profile_id is not None and (not isinstance(profile_id, str) or not profile_id.strip()))):
            raise ValueError("Estado inválido para recuperação")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT status,profile_id FROM story_languages WHERE story_id=? AND language=?",
                               (story_id, language)).fetchone()
            if row is None or status not in transitions.get(row[0], set()):
                raise ValueError("Transição exige estado gerenciado e reconciliado")
            profiles = {value[0] for value in conn.execute(
                "SELECT profile_id FROM story_languages WHERE story_id=? AND profile_id IS NOT NULL", (story_id,))}
            if len(profiles) > 1 or (profile_id is not None and profiles and profiles != {profile_id}):
                raise ValueError("Perfil do narrador não pode mudar entre idiomas")
            locked_profile = profile_id or row[1] or next(iter(profiles), None)
            conn.execute("UPDATE story_languages SET status=?,profile_id=?,reason_code=?,updated_at=? "
                         "WHERE story_id=? AND language=?",
                         (status, locked_profile, reason_code, datetime.now(timezone.utc).isoformat(), story_id, language))

    def retry_candidates(self, languages: list[str]) -> list[str]:
        """Fontes gerenciadas retomáveis, sem incluir processamento abandonado."""
        languages = _languages(languages)
        placeholders = ",".join("?" for _ in languages)
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT s.id FROM stories s JOIN story_languages l ON l.story_id=s.id "
                "WHERE s.source_sha256 IS NOT NULL AND l.status IN ('pending','unavailable') "
                f"AND l.language IN ({placeholders}) GROUP BY s.id ORDER BY MIN(l.updated_at),s.id", languages,
            ).fetchall()
        return [row[0] for row in rows]

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
            params = []
            if language:
                q += " AND language=?"
                params.append(language)
            rows = conn.execute(q, params).fetchall()
        return [dict(r) for r in rows]
