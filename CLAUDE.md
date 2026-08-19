# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A pipeline that turns Reddit stories into narrated, subtitled, vertical (9:16) short-form videos in three languages (Portuguese, English, Spanish), then queues them for YouTube/TikTok publishing. Built to run on a free stack: Reddit's public JSON endpoints (no API key), edge-tts/gTTS for voice, Whisper for subtitles, FFmpeg for rendering, Groq/Ollama for LLM steps, and SQLite for state.

All source comments and log messages are in Portuguese; keep new comments/log lines consistent with that unless told otherwise.

## Commands

```bash
# Run the full pipeline for one language (default: pt)
python main.py --lang pt
python main.py --lang pt en es

# Dry run — skips LLM/audio/video generation, just logs what would happen
python main.py --dry-run

# Skip extraction+filtering, use a hardcoded test story (see TEST_STORY in main.py)
python main.py --test-story --lang pt

# Run the background scheduler (cron-like jobs: generation + uploads + TikTok notify)
python -m scheduler.runner

# Tests
pytest
pytest tests/test_queue_tiktok.py
pytest tests/test_queue_tiktok.py::test_enqueue_creates_pending_item
```

There is no linter/formatter configured in this repo — don't assume `black`/`ruff` are wired in unless you check `requirements.txt` again.

FFmpeg must be installed and on PATH; Ollama is optional (local LLM fallback) and expected at `OLLAMA_URL` from `.env`.

## Architecture

### Full pipeline flow (`main.py`) — 1 story per run

`main.py` is a single-story-per-run orchestrator (`run_pipeline`). It instantiates one class per stage from `stages/` and `scheduler/notifier.py`, then walks through the steps below. The numbered step list in the `main.py` docstring is the authoritative source and must be kept in sync with this section whenever the order changes.

| # | Step | Module/detail |
|---|------|-----------------|
| 1 | Extraction | `stages/extractor.py` — public Reddit JSON (skipped with `--test-story`) |
| 2 | Filtering | `stages/filter.py` — score 0-100 |
| 3 | EN acronyms | Expands shorthand in the original text (`(28F)` → "28-year-old woman", `AITA`, `MIL`, etc. — see `expand_age_gender_en` / `REDDIT_ACRONYMS` in `main.py`) |
| 4 | Adaptation | `stages/adapter.py` — narrative cleanup via Groq (fallback: rules) |
| 4.5 | Validation | Validates the adapted (EN) script before translation |
| 5 | Translation | `stages/translator.py` — per language |
| 5.5 | Validation | Validates the translated script (per language) |
| 6 | PT/ES acronyms | Expands shorthand in the already-translated text (`expand_acronyms_translated`) |
| 7 | Gender detection | `stages/gender_detector.py` — **before** naturalization (deliberate ordering), so naturalization can start with correct gendered language from the outset |
| 8 | Naturalization | `stages/naturalizer.py` — LLM, with correct gender from the start |
| 9 | Validation | Fixes gender-agreement errors that slipped through naturalization |
| 9.5 | Validation | Validates the final script (adaptation + translation + gender + naturalization) |
| 10 | Title | `stages/titler.py` — viral generator based on the original Reddit title |
| 10.5 | Validation | Validates title + hook |
| 11 | Hook | Title injected as the first spoken line of the script |
| 12 | Split | `stages/splitter.py` — parts up to 2:45 (YouTube Shorts duration cap, with safety margin), each repeats the hook and gets its own closing |
| 13 | Voice | `stages/voice.py` — edge-tts, with the correct gendered voice |
| 14 | Subtitles | `stages/subtitle.py` — word-level animated ASS |
| 15 | Video | `stages/video.py` — FFmpeg 1080x1920 + ASS + automatic background (Shorts/) |
| 16 | Thumbnail | `stages/thumbnail.py` — Pillow (static JPG + animated .mov hook card with fade) |
| 17 | Metadata | `stages/metadata.py` — per-language SEO |
| 17.5 | Validation | Validates description + tags |
| 18 | Organization | `stages/organizer.py` — moves to `data/exports/{lang}/{slug}_{data}_{lang}.mp4` |

At the end, `scheduler/notifier.py` sends a Telegram summary (success/partial/failure), plus a per-video message for manual TikTok posting.

**Validation is threaded throughout, not just at the end.** `stages/validator.py` (`ValidatorEngine`) is called after adaptation, after each translation, after naturalization, after title/hook generation, and after metadata generation — each call can request an LLM-based rewrite ("surgical fix") of just the flagged span rather than regenerating the whole script. This is why the step numbering has half-steps (4.5, 5.5, 9.5, 10.5, 17.5): those are validation passes bolted onto the step before them.

**Note:** keep the `main.py` docstring synced with this list whenever the order changes.

### LLM fallback chain

Every stage that uses an LLM (`adapter.py`, `translator.py`, `naturalizer.py`, `gender_detector.py`, `titler.py`, `metadata.py`, `validator.py`) follows the same pattern: try the Groq API first (fast, needs `GROQ_API_KEY`) → fall back to local Ollama → fall back to hardcoded Python rules/templates. Model choice is deliberately tiered in `config/settings.yaml` — cheap 8B models (`llama-3.1-8b-instant`) for cleanup/detection tasks, and a bigger 70B model (`llama-3.3-70b-versatile`) only for the creative naturalization rewrite. When touching these stages, preserve the three-tier fallback rather than assuming Groq/Ollama is always available.

### Config layout

- `config/settings.yaml` — per-stage tuning (voice models, video dimensions, LLM model names, filtering thresholds). This is what `load_config()` in `main.py` reads at startup.
- `config/subreddits.yaml` — subreddit source list by category, flattened by `get_subreddits()`.
- `config/publishing.yaml` — everything for `scheduler/runner.py`: per-channel/per-language upload limits, posting-window schedules by weekday+timezone, growth-plan ramp (limits scale up by account age), TikTok notification windows, anti-detection jitter/pause settings.
- `config/voice_profiles.yaml` — TTS voice selection detail beyond what's in `settings.yaml`.
- `.env` (from `.env.example`) — secrets and per-environment values: `GROQ_API_KEY`, `OLLAMA_URL`, `TELEGRAM_BOT_TOKEN` + chat IDs per language, YouTube OAuth creds, `DRY_RUN`, `LOG_LEVEL`. Optional per-language Groq keys (`GROQ_API_KEY_PT`/`_EN`/`_ES`) give each language its own free-tier token budget instead of all three sharing one account's rate/daily limit — resolved by `utils/environment.py:groq_api_key(language)`, falling back to `GROQ_API_KEY` when a language-specific key isn't set.

### Scheduler / publishing (`scheduler/`)

`scheduler/runner.py` is a separate long-running process (APScheduler) from `main.py` — it doesn't render video itself, it shells out to `main.py` on a cron schedule and separately manages upload queues:

- `pipeline_job` — runs `main.py --lang <lang>` per configured language on a daily cron.
- `upload_job` — polls the YouTube queue (`scheduler/queue.py`) and fires `scheduler/uploader.py` when `_can_upload()` conditions are met (channel enabled, within posting window, under daily limit, past min interval since last upload, growth-plan-aware limits, random jitter/pause for anti-detection).
- `tiktok_notify_job` — TikTok has no automated upload here; instead it polls a separate TikTok queue and sends a Telegram message with the ready-to-post kit (video + caption + hashtags) for a human to post manually. An operator replies `/ok <id>`, `/fail <id>`, or `/skip <id>` in Telegram to resolve queue items (see `build_kit_message` in `scheduler/notifier.py` and the reply commands it embeds).
- `reset_daily_counters` — midnight UTC job resetting per-language upload counters.
- Queue state lives as JSON files (one per language) managed entirely through `scheduler/queue.py` functions (`enqueue`, `get_pending`, `update_status`, `count_uploads_today`, etc.) — there's no separate queue class, just module-level functions operating on `_QUEUE_DIR_PATHS`. Tests monkeypatch `_QUEUE_DIR_PATHS` to a tmp dir (see `tests/test_queue_tiktok.py`), so if you add queue functions keep state access going through that same module-level path list rather than hardcoding paths.

### Database

`utils/db.py` (`PipelineDB`) wraps a single SQLite file at `db/pipeline.db`, tracking story dedup (`story_exists`/`insert_story`) and per-language/per-part processing status (`update_status`/`get_pending`). This is pipeline-run state, separate from the JSON upload queues in `scheduler/queue.py`.

### Data directory conventions

`data/` holds pipeline artifacts, organized by language subdirectory within each stage: `data/raw/`, `data/scripts/{lang}/`, `data/audio/{lang}/`, `data/subtitles/{lang}/`, `data/videos/{lang}/`, `data/thumbnails/{lang}/`, `data/exports/{lang}/`. Final output filenames follow `{slug}_{YYYYMMDD}_{lang}[_pt{N}of{M}].mp4` (see `FileOrganizer.slugify` usage in `main.py`). Most of `data/` is gitignored except `data/scripts/` (final scripts + metadata JSON are checked in).

## Testing notes

Tests live in `tests/`, use `pytest`, and `conftest.py` just adds the repo root to `sys.path` (no package install needed). `tests/test_queue_tiktok.py` isolates queue state per test via the `use_temp_queue` autouse fixture — follow that pattern (monkeypatch `_QUEUE_DIR_PATHS`) for any new test touching `scheduler/queue.py` rather than pointing it at the real `data/queue/` files.

## Infrastructure

- The pipeline runs in production via Oracle Cloud (a cloud instance), not locally, when in production. Dev and test environments run locally.
- Groq API: no known quota limit, but calls respect a minimum interval defined between requests — don't remove/reduce that interval without confirming it's still needed.