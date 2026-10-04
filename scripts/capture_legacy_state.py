#!/usr/bin/env python3
"""Preservar cópia privada do cache legado, sem head nem decisão de upload."""
from __future__ import annotations

import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import zipfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.pipeline_state import _db_backup
from utils.pipeline_recovery import file_sha256
from utils.pipeline_snapshot import _under, LANGUAGES, MAX_CONTROL_BYTES, SnapshotError
from utils.pipeline_state import PrivateStateStore, StateError


def build_candidate(base: Path, cache_run_id: str, run_id: str) -> Path:
    if not all(re.fullmatch(r"[0-9]{1,20}", value) for value in (cache_run_id, run_id)):
        raise StateError("Identidade de candidato inválida")
    base = base.resolve()
    database = _under(base, base / "db/pipeline.db")
    if not database.is_file() or database.stat().st_size > MAX_CONTROL_BYTES:
        raise StateError("Banco candidato ausente ou excede limite")
    directory = _under(base, base / "data/state")
    directory.mkdir(parents=True, exist_ok=True)
    # Cada captura preserva sua cópia; não altera DB/fila nem ready.json.
    target = Path(tempfile.mkdtemp(prefix="legacy-candidate-", dir=directory))
    backup = target / "pipeline.db"
    _db_backup(database, backup)
    files = {"db/pipeline.db": backup}
    missing = []
    for language in LANGUAGES:
        name = f"data/queue/{language}.json"
        path = _under(base, base / name)
        if not path.is_file():
            missing.append(language)
            continue
        if path.stat().st_size > MAX_CONTROL_BYTES:
            raise StateError("Fila candidata excede limite")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("language") != language or not isinstance(data.get("items"), list):
            raise StateError("Fila candidata inválida")
        files[name] = path
    if sum(path.stat().st_size for path in files.values()) > MAX_CONTROL_BYTES:
        raise StateError("Candidato excede limite privado")
    manifest = {"format_version": 1, "authoritative": False, "cache_run_id": cache_run_id,
                "capture_run_id": run_id, "root": str(base), "missing_queues": missing,
                "files": {name: file_sha256(path) for name, path in files.items()}}
    archive_path = target / "candidate.zip"
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in files.items():
            archive.write(path, name)
        archive.writestr("candidate.json", json.dumps(manifest, ensure_ascii=False, sort_keys=True))
    with zipfile.ZipFile(archive_path) as archive:
        if any(hashlib.sha256(archive.read(name)).hexdigest() != digest for name, digest in manifest["files"].items()):
            raise StateError("Candidato mudou durante a captura")
    return archive_path


def main() -> int:
    try:
        cache_id = os.getenv("LEGACY_CACHE_RUN_ID", "")
        if (os.getenv("MATCHED_DB_CACHE_KEY") != f"pipeline-db-{cache_id}"
                or os.getenv("MATCHED_QUEUE_CACHE_KEY") != f"pipeline-queue-{cache_id}"):
            raise StateError("Os dois caches exatos devem ser restaurados")
        store = PrivateStateStore.from_environment(Path.cwd())
        if store.namespace != "legacy-inventory":
            raise StateError("Captura não escreve no namespace de produção")
        store.validate_target()
        path = build_candidate(Path.cwd(), cache_id, os.getenv("GITHUB_RUN_ID", ""))
        attempt = os.getenv("GITHUB_RUN_ATTEMPT", "1")
        if not re.fullmatch(r"[1-9][0-9]{0,8}", attempt):
            raise StateError("Tentativa de captura inválida")
        store._run_attempt = int(attempt)
        release = store._ensure_release(os.environ["GITHUB_RUN_ID"])
        # Sem complete-*.json: a captura jamais se torna head restaurável.
        store._put_asset(release, f"candidate-{cache_id}-{file_sha256(path)}.zip", path)
        print(f"Candidato legado preservado em destino privado; cache_run_id={cache_id}; sem bootstrap/publicação")
        return 0
    except (StateError, SnapshotError, OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        print("Captura bloqueada: candidato/cache/destino privado inválido")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
