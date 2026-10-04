#!/usr/bin/env python3
"""Salvar/restaurar estado privado; bootstrap explícito, sem upload YouTube."""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys
import tempfile

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.db import PipelineDB
from utils.pipeline_recovery import _write_json, file_sha256, json_sha256
from utils.pipeline_snapshot import (SnapshotError, build_snapshot, restore_snapshot, LANGUAGES,
                                     _under, _relative, _allowed_control, _allowed_media, _DB_PATH_FIELDS)
from utils.pipeline_state import (PrivateStateStore, StateError, StateMissing, require_ready,
                                  checkpoint_from_environment)


def _private_path(base: Path, value: str) -> Path:
    path = _under(base, Path(value))
    if not path.is_relative_to(base / "data/state"):
        raise StateError("Relatório de reconciliação deve ficar em data/state")
    return path


def _db_backup(path: Path, destination: Path) -> None:
    if not path.is_file():
        raise StateError("Banco obrigatório ausente")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(destination)) as dst:
        if src.execute("PRAGMA quick_check").fetchall() != [("ok",)]:
            raise StateError("Banco inválido; reconciliação necessária")
        src.backup(dst)


def _inventory(base: Path, db: Path) -> tuple[dict, dict]:
    """Só allowlist; hash lógico do backup também detecta mudanças no WAL."""
    inventory = {}
    details = {"legacy_story_ids": [], "recoverable_sources": [], "confirmed": [],
               "uncertain": [], "legacy_ambiguous": [], "missing_files": []}
    with tempfile.TemporaryDirectory(prefix="bootstrap-db-") as work:
        backup = Path(work) / "db.sqlite"
        _db_backup(db, backup)
        inventory["db/pipeline.db"] = file_sha256(backup)
        with closing(sqlite3.connect(backup)) as conn:
            columns = {row[1] for row in conn.execute("PRAGMA table_info(stories)")}
            if "id" not in columns:
                raise StateError("Schema legado não reconhecido")
            for story_id, digest in conn.execute("SELECT id," + ("source_sha256" if "source_sha256" in columns else "NULL") + " FROM stories"):
                details["recoverable_sources" if digest else "legacy_story_ids"].append(story_id)
    for directory in (base / "data/recovery", base / "data/scripts/profiles"):
        directory = _under(base, directory)
        if directory.exists():
            for path in directory.rglob("*.json"):
                name = _relative(base, path)
                if not _allowed_control(name):
                    raise StateError("Arquivo de recuperação fora da allowlist")
                inventory[name] = file_sha256(path)
    for language in LANGUAGES:
        name = f"data/queue/{language}.json"
        path = _under(base, base / name)
        inventory[name] = file_sha256(path) if path.exists() else None
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or not isinstance(data.get("items"), list):
            raise StateError("Fila legada inválida")
        for item in data["items"]:
            yt = item.get("platforms", {}).get("youtube", {})
            identity = {"language": language, "item_id": item["id"], "video_id": yt.get("video_id")}
            if yt.get("video_id"):
                details["confirmed"].append(identity)
            if yt.get("status") == "uploading" or item.get("status") == "uploading":
                details["uncertain"].append(identity)
            if not item.get("generation_key"):
                details["legacy_ambiguous"].append(identity)
            for field in ("video_path", "thumbnail_path"):
                if not item.get(field):
                    continue
                name = _relative(base, item[field])
                if not _allowed_media(name):
                    raise StateError("Referência de mídia fora da allowlist")
                file = _under(base, base / name)
                inventory[name] = file_sha256(file) if file.is_file() else None
                if not file.is_file():
                    details["missing_files"].append(name)
                if field == "video_path" and file.with_suffix(".json").is_file():
                    metadata = file.with_suffix(".json")
                    name = _relative(base, metadata)
                    if not _allowed_control(name):
                        raise StateError("Metadados fora da allowlist")
                    inventory[name] = file_sha256(metadata)
    return inventory, details


def _clone(base: Path, db: Path, inventory: dict) -> Path:
    state = _under(base, base / "data/state")
    state.mkdir(parents=True, exist_ok=True)
    staged = Path(tempfile.mkdtemp(prefix="bootstrap-", dir=state))
    database = staged / "db/pipeline.db"
    _db_backup(db, database)
    if file_sha256(database) != inventory["db/pipeline.db"]:
        raise StateError("Banco mudou durante o bootstrap")
    PipelineDB(database)  # Migração aditiva somente na cópia privada.
    for name, digest in inventory.items():
        if name == "db/pipeline.db" or digest is None:
            continue
        if not (_allowed_control(name) or _allowed_media(name)):
            raise StateError("Inventário fora da allowlist")
        source = _under(base, base / name)
        if file_sha256(source) != digest:
            raise StateError("Estado mudou durante o bootstrap")
        destination = staged / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    for language in LANGUAGES:
        path = staged / f"data/queue/{language}.json"
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {
            "language": language, "items": [], "uploads_today": 0, "last_upload_at": None}
        for item in data["items"]:
            for field in ("video_path", "thumbnail_path"):
                if item.get(field):
                    item[field] = str(staged / _relative(base, item[field]))
            if item.get("deleted_local_paths"):
                item["deleted_local_paths"] = {field: str(staged / _relative(base, value)) if value else None
                                               for field, value in item["deleted_local_paths"].items()}
        _write_json(path, data)
    with closing(sqlite3.connect(database)) as conn, conn:
        for row in conn.execute("SELECT id," + ",".join(_DB_PATH_FIELDS) + " FROM pipeline_parts").fetchall():
            values = [str(staged / _relative(base, value)) if value else None for value in row[1:]]
            conn.execute("UPDATE pipeline_parts SET " + ",".join(f"{field}=?" for field in _DB_PATH_FIELDS) + " WHERE id=?",
                         [*values, row[0]])
    return staged


def _snapshot(base: Path, namespace: str, *, name: str):
    return build_snapshot(base, base / "db/pipeline.db", snapshot_id=name, namespace=namespace,
                          run_id=os.getenv("GITHUB_RUN_ID", "0"), commit=os.getenv("GITHUB_SHA", "0"),
                          run_attempt=int(os.getenv("GITHUB_RUN_ATTEMPT", "1")))


def _report(base: Path, db: Path, namespace: str) -> dict:
    inventory, details = _inventory(base, db)
    report = {"format_version": 1, "namespace": namespace, "root": str(base), "inventory": inventory,
              "generated_at": datetime.now(timezone.utc).isoformat(), **details, "decisions": []}
    try:
        staged = _clone(base, db, inventory)
        candidate = _snapshot(staged, namespace, name="bootstrap-review")
        report["snapshot_candidate"] = {"valid": True, "manifest_sha256": json_sha256(candidate.manifest)}
    except (SnapshotError, StateError, OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        report["snapshot_candidate"] = {"valid": False, "reason_code": "reconciliation_required"}
    return report


def _apply_decisions(staged: Path, report: dict) -> None:
    required = {(entry["language"], entry["item_id"]) for group in ("uncertain", "legacy_ambiguous")
                for entry in report[group]}
    decisions = {}
    for decision in report.get("decisions", []):
        key = (decision["language"], decision["item_id"])
        if key in decisions or key not in required or decision.get("studio_checked") is not True:
            raise StateError("Decisão de reconciliação inválida")
        decisions[key] = decision
    if set(decisions) != required:
        raise StateError("Uploads legados/incertos exigem conferência explícita no Studio")
    for language in LANGUAGES:
        path = staged / f"data/queue/{language}.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data["items"]:
            decision = decisions.get((language, item["id"]))
            if not decision:
                continue
            yt = item["platforms"]["youtube"]
            action = decision["action"]
            if action == "retain_pending":
                if yt.get("video_id") or decision.get("confirmed_absent") is not True:
                    raise StateError("ID confirmado não pode voltar para pendente")
                yt["status"], item["status"] = "pending", "pending"
            elif action == "confirmed_uploaded":
                video_id = decision["video_id"]
                when = datetime.fromisoformat(decision["confirmed_at"])
                if (not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id) or when.tzinfo is None
                        or (yt.get("video_id") and yt["video_id"] != video_id)):
                    raise StateError("Confirmação externa incompatível")
                yt.update(status="uploaded", video_id=video_id, url=f"https://www.youtube.com/watch?v={video_id}")
                item["schedule"]["uploaded_at"] = when.isoformat()
                item["status"] = "partial" if item["platforms"].get("tiktok", {}).get("status") in {"pending", "notified"} else "uploaded"
            elif action == "cancel_unknown":
                if yt.get("video_id"):
                    raise StateError("Upload confirmado não pode ser cancelado implicitamente")
                yt["status"], item["status"] = "cancelled", "cancelled"
                item["platforms"]["tiktok"]["status"] = "cancelled"
            else:
                raise StateError("Ação de reconciliação inválida")
            if decision.get("tiktok") == "cancelled":
                item["platforms"]["tiktok"]["status"] = "cancelled"
                if yt["status"] == "uploaded":
                    item["status"] = "uploaded"
        _write_json(path, data)
    db = PipelineDB(staged / "db/pipeline.db")
    with closing(sqlite3.connect(db.db_path)) as conn:
        rows = conn.execute("SELECT story_id,language FROM story_languages WHERE status='processing'").fetchall()
    for story_id, language in rows:
        queue = json.loads((staged / f"data/queue/{language}.json").read_text(encoding="utf-8"))
        batch = [item for item in queue["items"] if item.get("story_id") == story_id and item.get("generation_key")]
        if any(item["platforms"]["youtube"]["status"] == "uploading" for item in batch):
            raise StateError("Efeito externo incerto impede retomar geração")
        # build_snapshot verifica fonte/perfil e completude do batch antes de publicação.
        db.set_language_status(story_id, language, "exported" if batch else "unavailable",
                               reason_code="reconciled_batch" if batch else "recovered_no_batch")


def _bootstrap(base: Path, db: Path, namespace: str, args, store: PrivateStateStore) -> None:
    try:
        existing = store.fetch_latest()
    except StateMissing:
        existing = None
    if existing is not None:
        if args.allow_empty_validation and namespace.startswith("validation-"):
            restore_snapshot(existing, base)
            return
        raise StateError("Namespace já tem head; use restore, não bootstrap")
    if args.allow_empty_validation:
        if not namespace.startswith("validation-") or args.reconciliation_file or args.confirm_digest:
            raise StateError("Bootstrap vazio é exclusivo de validação nova")
        # Nunca destruir dados presentes sob pretexto de começar um namespace vazio.
        if db.exists() or any((base / f"data/queue/{lang}.json").exists() for lang in LANGUAGES):
            raise StateError("Raiz de validação não está vazia")
        staged = Path(tempfile.mkdtemp(prefix="pipeline-empty-"))
        PipelineDB(staged / "db/pipeline.db")
        snapshot = _snapshot(staged, namespace, name="bootstrap-empty")
    else:
        if not args.reconciliation_file or not args.confirm_digest:
            raise StateError("Bootstrap exige relatório revisado e digest de confirmação")
        path = _private_path(base, args.reconciliation_file)
        if not re.fullmatch(r"[a-f0-9]{64}", args.confirm_digest) or file_sha256(path) != args.confirm_digest:
            raise StateError("Digest de aprovação incompatível")
        report = json.loads(path.read_text(encoding="utf-8"))
        inventory, details = _inventory(base, db)
        if (report.get("format_version") != 1 or report.get("namespace") != namespace or report.get("root") != str(base)
                or report["inventory"] != inventory
                or any(report.get(key) != value for key, value in details.items())):
            raise StateError("Estado mudou desde a revisão do bootstrap")
        staged = _clone(base, db, inventory)
        _apply_decisions(staged, report)
        snapshot = _snapshot(staged, namespace, name="bootstrap-reconciled")
        if _inventory(base, db)[0] != inventory:
            raise StateError("Estado mudou antes de confirmar bootstrap")
    store.publish(snapshot)
    restore_snapshot(snapshot, base)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estado privado verificável do pipeline")
    parser.add_argument("command", choices=("verify", "save", "restore", "bootstrap"))
    parser.add_argument("--base-dir", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--namespace", default=os.getenv("PIPELINE_STATE_NAMESPACE", ""))
    parser.add_argument("--db-path")
    parser.add_argument("--legacy-report")
    parser.add_argument("--reconciliation-file")
    parser.add_argument("--confirm-digest")
    parser.add_argument("--allow-empty-validation", action="store_true")
    args = parser.parse_args(argv)
    prior = {name: os.environ.get(name) for name in ("PIPELINE_STATE_NAMESPACE", "PIPELINE_DB_PATH")}
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", args.namespace):
            raise StateError("Namespace ausente ou inválido")
        base = Path(args.base_dir).resolve()
        _under(base, Path(args.base_dir))
        db = _under(base, Path(args.db_path) if args.db_path else base / "db/pipeline.db")
        os.environ["PIPELINE_STATE_NAMESPACE"], os.environ["PIPELINE_DB_PATH"] = args.namespace, str(db)
        if args.command == "verify" and args.legacy_report:
            _write_json(_private_path(base, args.legacy_report), _report(base, db, args.namespace))
            print("Relatório privado de reconciliação gerado; nenhum efeito externo.")
            return 0
        if args.command in {"restore", "bootstrap"}:
            store = PrivateStateStore.from_environment(base)
            if store.namespace != args.namespace:
                raise StateError("Namespace da credencial divergente")
            if args.command == "restore":
                restore_snapshot(store.fetch_latest(), base)
            else:
                _bootstrap(base, db, args.namespace, args, store)
        elif args.command == "save":
            checkpoint_from_environment(base, reason="cli_save")
        else:
            require_ready(base, args.namespace)
            snapshot = build_snapshot(base, db, snapshot_id="local-verify", namespace=args.namespace,
                                      run_id="0", commit="0")
            print(f"Snapshot validado: namespace={args.namespace}; arquivos={len(snapshot.manifest['files'])}; mídias={len(snapshot.media)}")
            return 0
        print(f"Estado confirmado: namespace={args.namespace}; operação={args.command}")
        return 0
    except StateError as error:
        print(f"Operação bloqueada: {error}", file=sys.stderr)
        return 2
    except (SnapshotError, OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        print("Operação bloqueada: estado privado ausente, incompatível ou corrompido", file=sys.stderr)
        return 2
    finally:
        for name, value in prior.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


if __name__ == "__main__":
    raise SystemExit(main())
