"""Fonte e checkpoints privados necessários à retomada da mesma geração."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile


def json_sha256(payload: dict | list) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _path(base_dir: Path, story_id: str, name: str) -> Path:
    if not isinstance(story_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", story_id):
        raise ValueError("ID inválido para recuperação")
    base = Path(base_dir).resolve()
    path = base / "data/recovery" / story_id / name
    if not path.resolve().is_relative_to(base) or any(p.is_symlink() for p in [path, *path.parents] if p != base):
        raise ValueError("Caminho de recuperação inválido")
    return path


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(payload, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_source(base_dir: Path, story: dict, source_hash: str, *, expanded_source: str) -> Path:
    from stages.narrator_profile import source_sha256
    path = _path(base_dir, story["id"], "source.json")
    if source_sha256(story.get("title", story["id"]), expanded_source) != source_hash:
        raise ValueError("Hash da fonte de recuperação inválido")
    payload = {"format_version": 1, "story": story, "expanded_source": expanded_source,
               "source_sha256": source_hash}
    if path.exists():
        if load_source(base_dir, story["id"], source_hash) != payload:
            raise ValueError("Fonte persistida não pode ser substituída")
        return path
    _write_json(path, payload)
    return path


def load_source(base_dir: Path, story_id: str, source_hash: str) -> dict:
    from stages.narrator_profile import source_sha256
    try:
        payload = json.loads(_path(base_dir, story_id, "source.json").read_text(encoding="utf-8"))
        story, expanded = payload["story"], payload["expanded_source"]
        if (payload["format_version"] != 1 or story["id"] != story_id
                or payload["source_sha256"] != source_hash
                or source_sha256(story.get("title", story_id), expanded) != source_hash):
            raise ValueError
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("Fonte de recuperação ausente ou inválida") from None


def _step_path(base_dir: Path, story_id: str, language: str, stage: str) -> Path:
    stages = {"adaptation", "translation", "naturalization", "title", "opening_hook", "closing_hook",
              "injected_hook", "prepared"}
    if (language not in {"pt", "en", "es"} or not isinstance(stage, str)
            or (stage not in stages and not re.fullmatch(r"(?:split_part|metadata|pre_tts)_part[1-3]", stage))):
        raise ValueError("Etapa/idioma de recuperação inválido")
    return _path(base_dir, story_id, f"{language}/{stage}.json")


def save_approved_step(base_dir: Path, story_id: str, language: str, stage: str, payload: dict) -> None:
    if (not isinstance(payload, dict) or not re.fullmatch(r"[a-f0-9]{64}", payload.get("source_sha256", ""))
            or not isinstance(payload.get("profile_id"), str) or not payload["profile_id"]):
        raise ValueError("Checkpoint aprovado inválido")
    envelope = {"format_version": 1, "payload": payload, "payload_sha256": json_sha256(payload)}
    _write_json(_step_path(base_dir, story_id, language, stage), envelope)


def load_approved_step(base_dir: Path, story_id: str, language: str, stage: str,
                       source_hash: str, profile_id: str) -> dict | None:
    path = _step_path(base_dir, story_id, language, stage)
    if not path.exists():
        return None
    try:
        envelope = json.loads(path.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        if envelope["format_version"] != 1 or json_sha256(payload) != envelope["payload_sha256"]:
            raise ValueError
        if payload["source_sha256"] != source_hash or payload["profile_id"] != profile_id:
            return None
        return payload
    except (OSError, ValueError, TypeError, KeyError):
        raise ValueError("Checkpoint de recuperação inválido") from None
