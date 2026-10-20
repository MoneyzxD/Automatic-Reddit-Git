#!/usr/bin/env python3
"""Testa armazenamento GitHub real com dados sintéticos e namespace exclusivo."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import sys
import tempfile
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import dotenv_values
from utils.db import PipelineDB
from utils.pipeline_recovery import file_sha256
from utils.pipeline_snapshot import build_snapshot, restore_snapshot
from utils.pipeline_state import APPROVED_REPO, PrivateStateStore, StateError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, help="Arquivo local com PIPELINE_STATE_TOKEN")
    args = parser.parse_args(argv)
    values = dotenv_values(args.env_file) if args.env_file else os.environ
    token = values.get("PIPELINE_STATE_TOKEN", "")
    namespace = "validation-storage-" + uuid4().hex[:12]
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    try:
        client = PrivateStateStore(APPROVED_REPO, token, namespace)
        with tempfile.TemporaryDirectory(prefix="probe-storage-") as directory:
            base = Path(directory)
            db = PipelineDB(base / "db/pipeline.db")
            snapshot = build_snapshot(base, db.db_path, snapshot_id="probe-1",
                                      namespace=namespace, run_id=run_id, commit="0")
            first = client.publish(snapshot)
            if client.publish(snapshot) != first:
                raise StateError("Repetição divergiu do checkpoint original")
            reader = PrivateStateStore(APPROVED_REPO, token, namespace)
            restored = reader.fetch_latest()
            restore_snapshot(restored, base / "restored")
            # O tamanho reproduz o blob que ficou starter no incidente de 20/10.
            path = base / "synthetic.bin"
            path.write_bytes(b"x" * 179222)
            digest = file_sha256(path)
            release = client._ensure_release(run_id)
            asset_id = client._put_asset(release, f"media-{digest}.bin", path)
            if client._put_asset(release, f"media-{digest}.bin", path) != asset_id:
                raise StateError("Repetição divergiu do blob original")
            downloaded = base / "downloaded.bin"
            reader._download(asset_id, downloaded, 179222)
            if downloaded.stat().st_size != 179222 or file_sha256(downloaded) != digest:
                raise StateError("Download sintético divergente")
        print(f"OK: checkpoint, repetição, restauração e blob real verificados; namespace={namespace}")
        print("Teste somente de armazenamento; não comprova geração nem publicação de vídeo.")
        return 0
    except (StateError, OSError):
        print("Falha no teste de armazenamento privado; nenhuma publicação YouTube executada.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
