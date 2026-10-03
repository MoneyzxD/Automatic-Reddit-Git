"""Estado durável em releases privadas; nenhum token implícito nem cleanup remoto."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from urllib.parse import urlparse

import requests

from utils.pipeline_recovery import file_sha256, json_sha256, _write_json
from utils.pipeline_snapshot import (Snapshot, SnapshotError, build_snapshot, verify_snapshot,
                                     restore_snapshot, _limit, MAX_CONTROL_BYTES, MAX_MEDIA_BYTES)

APPROVED_REPO = "MoneyzxD/Automatic-Reddit-State"
_ID = r"[A-Za-z0-9_-]{1,100}"
_HASH = r"[a-f0-9]{64}"
_DOWNLOAD_HOSTS = {"release-assets.githubusercontent.com", "objects.githubusercontent.com",
                   "github-releases.githubusercontent.com"}
_MARKER_LIMIT = 10 * 1024 * 1024


class StateError(RuntimeError):
    """Falha de confirmação/recuperação exige parar efeitos externos."""


class StateMissing(StateError):
    """Ausência provada por listagem autorizada, nunca por erro HTTP."""


def _integer(value) -> bool:
    return type(value) is int and value > 0


class PrivateStateStore:
    def __init__(self, repo: str, token: str, namespace: str, *, session=None):
        if (repo != APPROVED_REPO or not isinstance(token, str) or not token.strip()
                or not isinstance(namespace, str) or not re.fullmatch(_ID, namespace)):
            raise StateError("Configuração de estado privado ausente ou inválida")
        self.repo, self.namespace, self._token = repo, namespace, token
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False
        self.session.auth = None
        self.session.headers.pop("Authorization", None)
        self.base_dir = None
        self._run_attempt, self._sequence = 1, 0
        self._default_branch = None

    @classmethod
    def from_environment(cls, base_dir: Path) -> PrivateStateStore:
        store = cls(os.getenv("PIPELINE_STATE_REPO", ""), os.getenv("PIPELINE_STATE_TOKEN", ""),
                    os.getenv("PIPELINE_STATE_NAMESPACE", ""))
        store.base_dir = Path(base_dir).resolve()
        return store

    def _url(self, suffix: str = "") -> str:
        return f"https://api.github.com/repos/{self.repo}{suffix}"

    def _request(self, method: str, url: str, *, binary=False, signed=False, **kwargs):
        parsed = urlparse(url)
        hosts = _DOWNLOAD_HOSTS if signed else {"api.github.com", "uploads.github.com"}
        if (parsed.scheme != "https" or parsed.hostname not in hosts or parsed.username or parsed.password
                or parsed.port not in {None, 443} or parsed.fragment or method not in {"GET", "POST"}):
            raise StateError("Destino HTTP de estado não permitido")
        headers = {"Accept": "application/octet-stream" if binary else "application/vnd.github+json"}
        if not signed:
            headers.update(Authorization=f"Bearer {self._token}", **{"X-GitHub-Api-Version": "2022-11-28"})
        headers.update(kwargs.pop("headers", {}))
        try:
            return self.session.request(method, url, headers=headers, timeout=(15, 60), verify=True,
                                        allow_redirects=False, **kwargs)
        except requests.RequestException:
            raise StateError("API de estado privado indisponível") from None

    def _json(self, method: str, url: str, *, statuses=(200,), **kwargs):
        response = self._request(method, url, **kwargs)
        try:
            if response.status_code not in statuses:
                raise StateError("API de estado recusou a operação")
            return response.json()
        except (ValueError, TypeError):
            raise StateError("Resposta da API de estado inválida") from None
        finally:
            response.close()

    def validate_target(self) -> None:
        data = self._json("GET", self._url())
        if (not isinstance(data, dict) or data.get("full_name") != self.repo or data.get("private") is not True
                or not isinstance(data.get("default_branch"), str) or not data["default_branch"]):
            raise StateError("Destino não é o repositório privado aprovado")
        self._default_branch = data["default_branch"]

    def _pages(self, suffix: str) -> list[dict]:
        entries = []
        for page in range(1, 1001):
            data = self._json("GET", self._url(suffix), params={"per_page": 100, "page": page})
            if not isinstance(data, list) or any(not isinstance(entry, dict) for entry in data):
                raise StateError("Listagem de estado malformada")
            if not data:
                return entries
            entries.extend(data)
        raise StateError("Listagem excede capacidade; reconciliação necessária")

    def _ensure_release(self, run_id: str) -> dict:
        tag = f"state-{self.namespace}-{run_id}-{self._run_attempt}"
        response = self._request("GET", self._url(f"/releases/tags/{tag}"))
        try:
            if response.status_code == 404:
                data = self._json("POST", self._url("/releases"), statuses=(201,), json={
                    "tag_name": tag, "target_commitish": self._default_branch, "name": tag,
                    "body": "Snapshot privado verificável do pipeline.", "draft": False, "prerelease": True})
            elif response.status_code == 200:
                data = response.json()
            else:
                raise StateError("Não foi possível obter a release de estado")
        except (ValueError, TypeError):
            raise StateError("Release de estado inválida") from None
        finally:
            response.close()
        if not isinstance(data, dict) or not _integer(data.get("id")) or data.get("tag_name") != tag:
            raise StateError("Identidade de release divergente")
        return data

    def _assets(self, release: dict) -> list[dict]:
        if not _integer(release.get("id")):
            raise StateError("ID de release inválido")
        assets = self._pages(f"/releases/{release['id']}/assets")
        names = [asset.get("name") for asset in assets]
        if any(not isinstance(name, str) for name in names) or len(names) != len(set(names)):
            raise StateError("Inventário de assets conflitante")
        return assets

    def _download(self, asset_id: int, destination: Path, limit: int) -> None:
        if not _integer(asset_id):
            raise StateError("ID de asset inválido")
        response = self._request("GET", self._url(f"/releases/assets/{asset_id}"), binary=True, stream=True)
        try:
            for _ in range(5):
                if response.status_code != 302:
                    break
                location = response.headers.get("Location", "")
                response.close()
                response = self._request("GET", location, binary=True, signed=True, stream=True)
            if response.status_code != 200:
                raise StateError("Download de estado indisponível")
            total = 0
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    total += len(chunk)
                    if total > limit:
                        raise StateError("Asset de estado excede limite")
                    handle.write(chunk)
                handle.flush()
                os.fsync(handle.fileno())
        except (OSError, requests.RequestException):
            raise StateError("Download de estado interrompido") from None
        finally:
            response.close()

    def _check_asset(self, data: dict, name: str, size: int, digest: str) -> int:
        if (not isinstance(data, dict) or not _integer(data.get("id")) or data.get("name") != name
                or data.get("state") != "uploaded" or type(data.get("size")) is not int or data["size"] != size):
            raise StateError("Asset incompleto ou divergente")
        remote_digest = data.get("digest")
        if remote_digest:
            if remote_digest != f"sha256:{digest}":
                raise StateError("Hash remoto divergente")
        else:
            # APIs sem digest precisam comprovar bytes antes de publicar o marker.
            with tempfile.TemporaryDirectory(prefix="state-asset-") as work:
                path = Path(work) / "asset"
                self._download(data["id"], path, size)
                if path.stat().st_size != size or file_sha256(path) != digest:
                    raise StateError("Hash remoto não verificável")
        return data["id"]

    def _put_asset(self, release: dict, name: str, path: Path) -> int:
        size, digest = path.stat().st_size, file_sha256(path)
        existing = next((asset for asset in self._assets(release) if asset["name"] == name), None)
        if existing is not None:
            return self._check_asset(existing, name, size, digest)
        with path.open("rb") as handle:
            data = self._json("POST", f"https://uploads.github.com/repos/{self.repo}/releases/{release['id']}/assets",
                              statuses=(201,), params={"name": name}, data=handle,
                              headers={"Content-Type": "application/octet-stream", "Content-Length": str(size)})
        return self._check_asset(data, name, size, digest)

    def _upload_media(self, release: dict, media: dict[str, Path]) -> dict[str, int]:
        return {digest: self._put_asset(release, f"media-{digest}.bin", path) for digest, path in media.items()}

    def _upload_asset(self, release: dict, path: Path) -> int:
        return self._put_asset(release, f"payload-{self._sequence}-{file_sha256(path)}.tar.gz", path)

    def _upload_completion(self, release: dict, receipt: dict) -> None:
        with tempfile.TemporaryDirectory(prefix="state-complete-") as work:
            path = Path(work) / "receipt.json"
            _write_json(path, receipt)
            self._put_asset(release, f"complete-{self._sequence}.json", path)

    def _read_completion(self, asset: dict) -> dict:
        if (not _integer(asset.get("id")) or asset.get("state") != "uploaded"
                or type(asset.get("size")) is not int or not 0 < asset["size"] <= _MARKER_LIMIT):
            raise StateError("Marker de conclusão inválido")
        with tempfile.TemporaryDirectory(prefix="state-marker-") as work:
            path = Path(work) / "receipt.json"
            self._download(asset["id"], path, _MARKER_LIMIT)
            self._check_asset(asset, asset["name"], path.stat().st_size, file_sha256(path))
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if (not isinstance(data, dict) or data.get("namespace") != self.namespace
                        or data["manifest"]["namespace"] != self.namespace
                        or data["snapshot_id"] != data["manifest"]["snapshot_id"]
                        or not _integer(data["payload_id"]) or not isinstance(data["media_ids"], dict)
                        or set(data["media_ids"]) != set(data["manifest"]["media"])
                        or any(not _integer(value) for value in data["media_ids"].values())):
                    raise ValueError
                return data
            except (ValueError, TypeError, KeyError):
                raise StateError("Marker de conclusão corrompido") from None

    def publish(self, snapshot: Snapshot) -> dict:
        try:
            self.validate_target()
            verify_snapshot(snapshot)
            if snapshot.namespace != self.namespace:
                raise StateError("Namespace do snapshot divergente")
            self._run_attempt, self._sequence = snapshot.manifest["run_attempt"], snapshot.manifest["sequence"]
            release = self._ensure_release(snapshot.manifest["run_id"])
            marker = next((asset for asset in self._assets(release) if asset["name"] == f"complete-{self._sequence}.json"), None)
            if marker is not None:
                receipt = self._read_completion(marker)
                if receipt["manifest"] != snapshot.manifest:
                    raise StateError("Snapshot já publicado com conteúdo diferente")
                self._fetch_receipt(receipt)
                return receipt
            media_ids = self._upload_media(release, snapshot.media)
            payload_id = self._upload_asset(release, snapshot.payload_path)
            # Os bytes locais também devem permanecer íntegros até o commit remoto.
            verify_snapshot(snapshot)
            receipt = {"snapshot_id": snapshot.snapshot_id, "namespace": self.namespace,
                       "manifest": snapshot.manifest, "payload_id": payload_id, "media_ids": media_ids}
            self._upload_completion(release, receipt)
            return receipt
        except (SnapshotError, OSError, ValueError, TypeError, KeyError):
            raise StateError("Falha ao confirmar estado privado") from None

    def _markers(self) -> list[tuple[tuple[int, int, int], dict]]:
        self.validate_target()
        pattern = rf"state-{re.escape(self.namespace)}-([0-9]+)-([0-9]+)"
        markers = []
        for release in self._pages("/releases"):
            match = re.fullmatch(pattern, release.get("tag_name", ""))
            if not match:
                continue
            for asset in self._assets(release):
                sequence = re.fullmatch(r"complete-([0-9]+)\.json", asset["name"])
                if sequence:
                    markers.append(((int(match[1]), int(match[2]), int(sequence[1])), asset))
        keys = [key for key, _ in markers]
        if len(set(keys)) != len(keys):
            raise StateError("Heads de estado conflitantes")
        return sorted(markers, key=lambda entry: entry[0], reverse=True)

    def _fetch_receipt(self, receipt: dict) -> Snapshot:
        manifest = receipt["manifest"]
        if self.base_dir:
            state = self.base_dir / "data/state"
            state.mkdir(parents=True, exist_ok=True)
            work = Path(tempfile.mkdtemp(prefix="download-", dir=state))
        else:
            work = Path(tempfile.mkdtemp(prefix="pipeline-state-"))
        payload = work / "payload.tar.gz"
        self._download(receipt["payload_id"], payload, _limit("CONTROL", MAX_CONTROL_BYTES) + 10 * 1024 * 1024)
        media = {}
        for digest, asset_id in receipt["media_ids"].items():
            if not re.fullmatch(_HASH, digest):
                raise StateError("Hash de mídia inválido")
            path = work / f"{digest}.bin"
            self._download(asset_id, path, _limit("MEDIA", MAX_MEDIA_BYTES))
            media[digest] = path
        snapshot = Snapshot(receipt["snapshot_id"], self.namespace, manifest, payload, media)
        verify_snapshot(snapshot)
        return snapshot

    def fetch_latest(self) -> Snapshot:
        try:
            markers = self._markers()
            if not markers:
                raise StateMissing("Nenhum snapshot completo no namespace autorizado")
            key, asset = markers[0]
            receipt = self._read_completion(asset)
            manifest = receipt["manifest"]
            if key != (int(manifest["run_id"]), manifest["run_attempt"], manifest["sequence"]):
                raise StateError("Marker e identidade do run divergentes")
            return self._fetch_receipt(receipt)
        except (SnapshotError, OSError, ValueError, TypeError, KeyError):
            raise StateError("Último snapshot completo inválido; reconciliação necessária") from None


def require_ready(base_dir: Path, namespace: str) -> dict:
    base = Path(base_dir).resolve()
    try:
        if (base / "data/state/restoring.json").exists():
            raise StateError("Restauração incompleta; operação bloqueada")
        ready = json.loads((base / "data/state/ready.json").read_text(encoding="utf-8"))
        if (ready.get("format_version") != 1 or ready.get("namespace") != namespace
                or ready.get("root") != str(base) or not re.fullmatch(_HASH, ready["manifest_sha256"])
                or type(ready["sequence"]) is not int or ready["sequence"] < 0):
            raise ValueError
        return ready
    except (OSError, ValueError, TypeError, KeyError):
        raise StateError("Estado não restaurado ou recibo incompatível") from None


def checkpoint_from_environment(base_dir: Path, *, reason: str) -> dict:
    """Reserva sequência antes do envio; falha não apaga nem substitui o head."""
    try:
        from utils.environment import db_path
        base = Path(base_dir).resolve()
        store = PrivateStateStore.from_environment(base)
        ready = require_ready(base, store.namespace)
        run_id = os.getenv("GITHUB_RUN_ID", "0")
        attempt = int(os.getenv("GITHUB_RUN_ATTEMPT", "1"))
        commit = os.getenv("GITHUB_SHA", "0")
        sequence_path = base / "data/state/sequence.json"
        previous = ready["sequence"]
        if sequence_path.exists():
            saved = json.loads(sequence_path.read_text(encoding="utf-8"))
            if (saved["namespace"] != store.namespace or saved["root"] != str(base)
                    or type(saved["sequence"]) is not int or saved["sequence"] < 0):
                raise StateError("Contador de checkpoint incompatível")
            previous = max(previous, saved["sequence"])
        sequence = previous + 1
        _write_json(sequence_path, {"namespace": store.namespace, "root": str(base),
                                   "run_id": run_id, "run_attempt": attempt, "sequence": sequence})
        snapshot = build_snapshot(base, db_path(base), snapshot_id=f"{run_id}-{attempt}-{sequence}",
                                  namespace=store.namespace, run_id=run_id, commit=commit,
                                  run_attempt=attempt, sequence=sequence)
        receipt = store.publish(snapshot)
        _write_json(base / "data/state/last_saved.json", {"snapshot_id": snapshot.snapshot_id,
                    "namespace": store.namespace, "root": str(base), "sequence": sequence,
                    "manifest_sha256": json_sha256(snapshot.manifest)})
        return receipt
    except (SnapshotError, OSError, ValueError, TypeError, KeyError):
        raise StateError("Checkpoint privado não confirmado") from None
