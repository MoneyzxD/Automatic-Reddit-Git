"""Bundle privado, verificável e portátil; nenhuma operação de rede."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sqlite3
import tarfile
import tempfile

from utils.pipeline_recovery import file_sha256, json_sha256, _write_json

MAX_CONTROL_BYTES = 100 * 1024 * 1024
MAX_MEDIA_BYTES = 1024 * 1024 * 1024
LANGUAGES = ("pt", "pt-br", "en", "es")
_ID = r"[A-Za-z0-9_-]+"
_HASH = r"[a-f0-9]{64}"
_STAGES = r"(?:adaptation|translation|naturalization|title|opening_hook|closing_hook|injected_hook|prepared|(?:split_part|metadata|pre_tts)_part[1-3])"
_DB_PATH_FIELDS = ("audio_path", "subtitle_path", "video_path", "thumbnail_path", "metadata_path", "export_path")


class SnapshotError(RuntimeError):
    """Estado inválido não autoriza iniciar uma fila vazia."""


@dataclass(frozen=True)
class Snapshot:
    snapshot_id: str
    namespace: str
    manifest: dict
    payload_path: Path
    media: dict[str, Path]


def _limit(kind: str, default: int) -> int:
    value = os.getenv(f"PIPELINE_STATE_{kind}_MAX_BYTES", str(default))
    if not re.fullmatch(r"[1-9][0-9]{0,11}", value):
        raise SnapshotError("Limite de snapshot inválido")
    return int(value)


def safe_member_name(name: str) -> PurePosixPath:
    if not isinstance(name, str):
        raise SnapshotError("Caminho inválido no snapshot")
    path = PurePosixPath(name)
    if (not name or "\\" in name or ":" in name or "\x00" in name or path.is_absolute()
            or ".." in path.parts or str(path) != name or name == "."):
        raise SnapshotError("Caminho inválido no snapshot")
    return path


def _allowed_control(name: str) -> bool:
    safe_member_name(name)
    if re.search(r"token|credentials|\.env", name, re.IGNORECASE):
        return False
    return bool(name == "db/pipeline.db"
                or re.fullmatch(r"data/queue/(?:pt|pt-br|en|es)\.json", name)
                or re.fullmatch(rf"data/recovery/{_ID}/source\.json", name)
                or re.fullmatch(rf"data/recovery/{_ID}/(?:pt|en|es)/{_STAGES}\.json", name)
                or re.fullmatch(rf"data/scripts/profiles/{_ID}_narrator_profile\.json", name)
                or re.fullmatch(rf"data/scripts/(?:pt|en|es)/{_ID}(?:_meta\.json|\.txt)", name)
                or re.fullmatch(rf"data/exports/(?:pt|pt-br|en|es)/(?:{_ID}/)*{_ID}\.json", name))


def _allowed_media(name: str) -> bool:
    safe_member_name(name)
    return bool(re.fullmatch(rf"data/(?:exports|videos|thumbnails)/(?:pt|pt-br|en|es)/(?:{_ID}/)*{_ID}\.(?:mp4|jpg)", name))


def _under(base: Path, path: Path) -> Path:
    path = Path(path)
    if not path.is_absolute():
        path = base / path
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents):
        raise SnapshotError("Links não são permitidos no estado")
    if path.is_file() and path.stat().st_nlink > 1:
        raise SnapshotError("Hardlinks não são permitidos no estado")
    path = path.resolve()
    if not path.is_relative_to(base):
        raise SnapshotError("Referência fora da raiz do estado")
    return path


def _relative(base: Path, value: str | Path) -> str:
    return _under(base, Path(value)).relative_to(base).as_posix()


def _json_bytes(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _needs_media(item: dict) -> bool:
    platforms = item["platforms"]
    yt = platforms["youtube"]
    return (yt["status"] not in {"uploaded", "cancelled"}
            or platforms.get("tiktok", {}).get("status") in {"pending", "notified"}
            or yt.get("thumbnail_status") == "failed")


def _validate_queue(data: dict, language: str) -> None:
    if (not isinstance(data, dict) or data.get("language") != language
            or not isinstance(data.get("items"), list)):
        raise SnapshotError("Schema da fila inválido")
    ids = set()
    for item in data["items"]:
        if (not isinstance(item, dict) or not isinstance(item.get("id"), str) or not item["id"]
                or item["id"] in ids or not isinstance(item.get("schedule"), dict)
                or item.get("status") not in {"pending", "uploading", "uploaded", "partial", "failed", "cancelled"}
                or not isinstance(item.get("metadata"), dict) or not isinstance(item.get("platforms"), dict)
                or not isinstance(item["platforms"].get("youtube"), dict)
                or item["platforms"]["youtube"].get("status") not in {"pending", "uploading", "uploaded", "failed", "cancelled"}
                or not isinstance(item.get("video_path"), str) or not item["video_path"]):
            raise SnapshotError("Item de fila inválido")
        if item["platforms"]["youtube"]["status"] == "uploaded" and not item["platforms"]["youtube"].get("video_id"):
            raise SnapshotError("Upload confirmado sem ID")
        ids.add(item["id"])


def _db_records(path: Path) -> tuple[list, list]:
    with closing(sqlite3.connect(path)) as conn:
        if conn.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise SnapshotError("Banco inconsistente")
        for table, columns in {"stories": {"id", "source_sha256"},
                               "story_languages": {"story_id", "language", "status", "profile_id"},
                               "pipeline_parts": {"story_id", "language", *_DB_PATH_FIELDS}}.items():
            found = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            if not columns <= found:
                raise SnapshotError("Schema do banco incompatível")
        sources = conn.execute("SELECT id, source_sha256 FROM stories WHERE source_sha256 IS NOT NULL").fetchall()
        languages = conn.execute("SELECT story_id, language, status, profile_id FROM story_languages").fetchall()
    ids = {story_id for story_id, _ in sources}
    for story_id, digest in sources:
        if not isinstance(story_id, str) or not re.fullmatch(_ID, story_id) or not re.fullmatch(_HASH, digest):
            raise SnapshotError("Identidade de fonte inválida")
    for story_id, language, status, profile_id in languages:
        if (story_id not in ids or language not in {"pt", "en", "es"}
                or status not in {"pending", "processing", "unavailable", "rejected", "exported"}
                or (status in {"processing", "exported", "rejected"} and not profile_id)):
            raise SnapshotError("Estado de geração inválido")
    return sources, languages


def _validate_control(directory: Path, manifest: dict) -> None:
    from stages.narrator_profile import load_profile
    from utils.pipeline_recovery import load_source, load_approved_step
    sources, rows = _db_records(directory / "db/pipeline.db")
    source_ids = {story_id for story_id, _ in sources}
    profile_ids = {}
    for story_id, digest in sources:
        load_source(directory, story_id, digest)
        locked = {row[3] for row in rows if row[0] == story_id and row[3]}
        if len(locked) > 1:
            raise SnapshotError("Perfis divergentes para a mesma fonte")
        if locked:
            path = directory / f"data/scripts/profiles/{story_id}_narrator_profile.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = load_profile(story_id, directory, digest, data["resolver_version"])
            if profile is None or profile.profile_id not in locked:
                raise SnapshotError("Perfil de recuperação incompatível")
            profile_ids[story_id] = profile.profile_id
        for name in manifest["files"]:
            match = re.fullmatch(rf"data/recovery/{re.escape(story_id)}/(pt|en|es)/(.+)\.json", name)
            if match:
                if story_id not in profile_ids or load_approved_step(
                        directory, story_id, match[1], match[2], digest, profile_ids[story_id]) is None:
                    raise SnapshotError("Checkpoint incompatível com a fonte")
    media_paths = {}
    for digest, info in manifest["media"].items():
        if not re.fullmatch(_HASH, digest) or type(info["size"]) is not int or info["size"] < 0 or not info["paths"]:
            raise SnapshotError("Manifesto de mídia inválido")
        for name in info["paths"]:
            if not _allowed_media(name) or name in media_paths:
                raise SnapshotError("Referência de mídia inválida")
            media_paths[name] = digest
    queue_mapping = {}
    referenced = set()
    for lang in LANGUAGES:
        name = f"data/queue/{lang}.json"
        data = json.loads((directory / name).read_text(encoding="utf-8"))
        _validate_queue(data, lang)
        mapping = {}
        for item in data["items"]:
            mapping[item["id"]] = {}
            for field in ("video_path", "thumbnail_path"):
                value = item.get(field)
                if value:
                    if not _allowed_media(value):
                        raise SnapshotError("Caminho de mídia inválido na fila")
                    if _needs_media(item) and value not in media_paths:
                        raise SnapshotError("Mídia pendente não recuperável")
                    if value in media_paths:
                        referenced.add(value)
                mapping[item["id"]][field] = value
            if item.get("generation_key"):
                story_id = item.get("story_id")
                if (story_id not in source_ids or story_id not in profile_ids
                        or item["metadata"].get("narrator_profile_id") != profile_ids[story_id]):
                    raise SnapshotError("Fila e perfil de geração incompatíveis")
        queue_mapping[name] = mapping
    if queue_mapping != manifest["queue_paths"] or set(media_paths) != referenced:
        raise SnapshotError("Mappings da fila divergentes do manifesto")


def build_snapshot(base_dir: Path, db_path: Path, *, snapshot_id: str, namespace: str,
                   run_id: str, commit: str, run_attempt: int = 1, sequence: int = 0) -> Snapshot:
    """Congela DB consistente e inventário explícito, sem varrer o workspace."""
    try:
        if (not re.fullmatch(_ID, snapshot_id) or not re.fullmatch(_ID, namespace)
                or not re.fullmatch(r"[0-9]+", run_id) or not re.fullmatch(r"[a-fA-F0-9]{1,64}", commit)
                or type(run_attempt) is not int or run_attempt < 1 or type(sequence) is not int or sequence < 0):
            raise SnapshotError("Identidade do snapshot inválida")
        control_limit = _limit("CONTROL", MAX_CONTROL_BYTES)
        media_limit = _limit("MEDIA", MAX_MEDIA_BYTES)
        base = Path(base_dir).resolve()
        _under(base, Path(base_dir))
        source_db = _under(base, db_path)
        if not source_db.is_file():
            raise SnapshotError("Banco obrigatório ausente")
        state_dir = _under(base, base / "data/state")
        state_dir.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix=f"snapshot-{snapshot_id}-", dir=state_dir))
        control = work / "control"
        (control / "db").mkdir(parents=True)
        backup = control / "db/pipeline.db"
        with closing(sqlite3.connect(source_db)) as src, closing(sqlite3.connect(backup)) as dst:
            src.backup(dst)
        sources, _ = _db_records(backup)
        manifest = {"format_version": 1, "snapshot_id": snapshot_id, "namespace": namespace,
                    "run_id": run_id, "run_attempt": run_attempt, "commit": commit, "sequence": sequence,
                    "files": {}, "media": {}, "queue_paths": {}}
        media = {}
        def copy_control(path: Path):
            relative = _relative(base, path)
            if not _allowed_control(relative):
                raise SnapshotError("Arquivo fora da allowlist do estado")
            destination = control / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        for story_id, _ in sources:
            source = _under(base, base / f"data/recovery/{story_id}")
            if not source.is_dir():
                raise SnapshotError("Fonte gerenciada ausente")
            for path in source.rglob("*.json"):
                copy_control(_under(base, path))
            profile = _under(base, base / f"data/scripts/profiles/{story_id}_narrator_profile.json")
            if profile.exists():
                copy_control(profile)
        for language in LANGUAGES:
            name = f"data/queue/{language}.json"
            path = _under(base, base / name)
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
            else:
                # Bundle inicial explicita todas as filas; restore nunca as presume vazias.
                data = {"language": language, "items": [], "uploads_today": 0, "last_upload_at": None}
            _validate_queue(data, language)
            mapping = {}
            for item in data["items"]:
                mapping[item["id"]] = {}
                for field in ("video_path", "thumbnail_path"):
                    value = item.get(field)
                    if value:
                        file = _under(base, Path(value))
                        value = _relative(base, file)
                        if not _allowed_media(value):
                            raise SnapshotError("Mídia fora da allowlist")
                        if _needs_media(item) and not file.is_file():
                            raise SnapshotError("Mídia pendente ausente")
                        if file.is_file():
                            size = file.stat().st_size
                            if size > media_limit:
                                raise SnapshotError("Mídia excede limite configurado")
                            digest = file_sha256(file)
                            media[digest] = file
                            info = manifest["media"].setdefault(digest, {"size": size, "paths": []})
                            if value not in info["paths"]:
                                info["paths"].append(value)
                            if field == "video_path" and file.with_suffix(".json").is_file():
                                copy_control(_under(base, file.with_suffix(".json")))
                    item[field] = value
                    mapping[item["id"]][field] = value
                # Metadados embutidos + prepared/checkpoints bastam à retomada; final.txt é evidência opcional.
            manifest["queue_paths"][name] = mapping
            _write_json(control / name, data)
        # Paths de partes também são relativos; referência legada externa bloqueia bootstrap.
        with closing(sqlite3.connect(backup)) as conn, conn:
            fields = ",".join(_DB_PATH_FIELDS)
            for row in conn.execute(f"SELECT id,{fields} FROM pipeline_parts").fetchall():
                values = [_relative(base, value) if value else None for value in row[1:]]
                conn.execute("UPDATE pipeline_parts SET " + ",".join(f"{field}=?" for field in _DB_PATH_FIELDS) + " WHERE id=?",
                             [*values, row[0]])
        total = 0
        for path in sorted(control.rglob("*")):
            if not path.is_file():
                continue
            size = path.stat().st_size
            total += size
            if total > control_limit:
                raise SnapshotError("Control-plane excede limite configurado")
            manifest["files"][path.relative_to(control).as_posix()] = {"size": size, "sha256": file_sha256(path)}
        payload = work / "payload.tar.gz"
        with tarfile.open(payload, "w:gz") as archive:
            for name in manifest["files"]:
                archive.add(control / name, arcname=name, recursive=False)
        manifest["payload_sha256"] = file_sha256(payload)
        snapshot = Snapshot(snapshot_id, namespace, manifest, payload, media)
        verify_snapshot(snapshot)
        return snapshot
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, tarfile.TarError):
        raise SnapshotError("Falha ao construir snapshot íntegro") from None


def _extract_verified(snapshot: Snapshot, destination: Path) -> None:
    manifest = snapshot.manifest
    control_limit = _limit("CONTROL", MAX_CONTROL_BYTES)
    media_limit = _limit("MEDIA", MAX_MEDIA_BYTES)
    if (manifest.get("format_version") != 1 or manifest["snapshot_id"] != snapshot.snapshot_id
            or manifest["namespace"] != snapshot.namespace or not re.fullmatch(_ID, snapshot.snapshot_id)
            or not re.fullmatch(_ID, snapshot.namespace) or type(manifest["sequence"]) is not int
            or manifest["sequence"] < 0 or not re.fullmatch(r"[0-9]+", manifest["run_id"])
            or type(manifest["run_attempt"]) is not int or manifest["run_attempt"] < 1
            or snapshot.payload_path.stat().st_size > control_limit + 10 * 1024 * 1024
            or file_sha256(snapshot.payload_path) != manifest["payload_sha256"]):
        raise SnapshotError("Manifesto ou payload inválido")
    if set(snapshot.media) != set(manifest["media"]):
        raise SnapshotError("Conjunto de mídia incompleto")
    for digest, file in snapshot.media.items():
        if (file.is_symlink() or any(parent.is_symlink() for parent in file.parents)
                or file.stat().st_nlink > 1 or file.stat().st_size > media_limit
                or file.stat().st_size != manifest["media"][digest]["size"] or file_sha256(file) != digest):
            raise SnapshotError("Mídia corrompida ou acima do limite")
    names, total = set(), 0
    with tarfile.open(snapshot.payload_path, "r:gz") as archive:
        for member in archive:
            name = member.name
            if not member.isreg() or name in names or not _allowed_control(name):
                raise SnapshotError("Membro inválido no bundle")
            info = manifest["files"].get(name)
            if not info or type(info["size"]) is not int or member.size != info["size"] or member.size < 0:
                raise SnapshotError("Tamanho divergente no bundle")
            total += member.size
            if total > control_limit or len(names) >= 100000:
                raise SnapshotError("Bundle excede limite configurado")
            path = destination / name
            path.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            with archive.extractfile(member) as src, path.open("wb") as dst:
                for block in iter(lambda: src.read(1024 * 1024), b""):
                    digest.update(block)
                    dst.write(block)
            if digest.hexdigest() != info["sha256"]:
                raise SnapshotError("Hash de arquivo divergente")
            names.add(name)
    if names != set(manifest["files"]):
        raise SnapshotError("Bundle incompleto")
    _validate_control(destination, manifest)


def verify_snapshot(snapshot: Snapshot) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="pipeline-verify-") as work:
            _extract_verified(snapshot, Path(work))
    except (OSError, ValueError, TypeError, KeyError, AttributeError, sqlite3.Error, tarfile.TarError):
        raise SnapshotError("Snapshot ausente, incompatível ou corrompido") from None


def restore_snapshot(snapshot: Snapshot, target_dir: Path) -> None:
    """Verifica antes de tocar ativos; falha no commit conserva marker/preimagem."""
    verify_snapshot(snapshot)
    try:
        target = Path(target_dir).resolve()
        _under(target, Path(target_dir))
        state = _under(target, target / "data/state")
        state.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="restore-", dir=state))
        staged, preimage = work / "staged", work / "preimage"
        _extract_verified(snapshot, staged)
        for digest, info in snapshot.manifest["media"].items():
            for name in info["paths"]:
                path = staged / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(snapshot.media[digest], path)
        for lang in LANGUAGES:
            path = staged / f"data/queue/{lang}.json"
            data = json.loads(path.read_text(encoding="utf-8"))
            for item in data["items"]:
                for field in ("video_path", "thumbnail_path"):
                    if item.get(field):
                        item[field] = str(_under(target, target / item[field]))
            _write_json(path, data)
        with closing(sqlite3.connect(staged / "db/pipeline.db")) as conn, conn:
            fields = ",".join(_DB_PATH_FIELDS)
            for row in conn.execute(f"SELECT id,{fields} FROM pipeline_parts").fetchall():
                values = [str(_under(target, target / str(safe_member_name(value)))) if value else None for value in row[1:]]
                conn.execute("UPDATE pipeline_parts SET " + ",".join(f"{field}=?" for field in _DB_PATH_FIELDS) + " WHERE id=?",
                             [*values, row[0]])
        paths = list(snapshot.manifest["files"])
        paths.extend(name for info in snapshot.manifest["media"].values() for name in info["paths"])
        for name in paths:
            active = _under(target, target / name)
            if active.exists():
                prior = preimage / name
                prior.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(active, prior)
        receipt = {"format_version": 1, "snapshot_id": snapshot.snapshot_id, "namespace": snapshot.namespace,
                   "root": str(target), "manifest_sha256": json_sha256(snapshot.manifest),
                   "run_id": snapshot.manifest["run_id"], "run_attempt": snapshot.manifest["run_attempt"],
                   "sequence": snapshot.manifest["sequence"]}
        _write_json(state / "restoring.json", receipt)
        for name in paths:
            active = _under(target, target / name)
            active.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged / name, active)
        _write_json(state / "ready.json", receipt)
        (state / "restoring.json").unlink()
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error, tarfile.TarError):
        raise SnapshotError("Restauração interrompida; reconciliação necessária") from None
