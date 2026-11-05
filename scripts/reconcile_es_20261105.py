"""Reparo delimitado do recibo perdido em05/11; nenhuma escrita no YouTube."""
import json
import os
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scheduler import queue
from utils.pipeline_state import StateError, require_ready, checkpoint_from_environment

ITEM = "1x3uxdj_es"
VIDEO = "cxV3V4z7Kwc"
CHANNEL = "UCAMHj4K_q2qWu9LEVgbwfoA"


def reconcile(base, youtube):
    require_ready(base, "production")
    items = queue._load_queue("es")["items"]
    row = next((x for x in items if x["id"] == ITEM), None)
    if row is None:
        raise StateError("Item conhecido não encontrado")
    state = row["platforms"]["youtube"]
    if state.get("video_id") not in {None, VIDEO} or state["status"] not in {"uploading", "uploaded"}:
        raise StateError("Estado divergente; reconciliação recusada")
    if any(x["id"] != ITEM and x["platforms"]["youtube"].get("video_id") == VIDEO for x in items):
        raise StateError("ID já atribuído a outro item")
    owners = youtube.channels().list(part="id", mine=True).execute().get("items", [])
    videos = youtube.videos().list(part="snippet,status,contentDetails", id=VIDEO).execute().get("items", [])
    if len(owners) != 1 or owners[0].get("id") != CHANNEL or len(videos) != 1:
        raise StateError("Canal/vídeo não confirmado pela API")
    video = videos[0]
    snippet = video["snippet"]
    expected = row["metadata"]["youtube"]
    if (video["id"] != VIDEO or snippet.get("channelId") != CHANNEL
            or snippet.get("title") != expected["title"]
            or snippet.get("description") != expected["description"]
            or snippet.get("publishedAt") != "2026-11-05T15:58:02Z"
            or video["status"].get("privacyStatus") != "public"
            or video["status"].get("uploadStatus") != "processed"
            or video["contentDetails"].get("duration") != "PT2M29S"):
        raise StateError("Evidência externa divergente; nada alterado")
    if state["status"] == "uploaded":
        print("Recibo já confirmado; nenhuma alteração")
        return
    checkpoint_from_environment(base, reason="reconciliation_preflight")
    queue.update_status("es", ITEM, "youtube", "uploaded", video_id=VIDEO,
                        url=f"https://youtu.be/{VIDEO}", publish_at=snippet["publishedAt"],
                        thumbnail={"status": "missing", "reason": "receipt_reconciled_without_thumbnail_confirmation"})
    checkpoint_from_environment(base, reason="reconciliation_confirmed")
    print(f"Recibo ES confirmado e persistido: {VIDEO}; nenhum upload executado")


def main():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    if os.environ.get("GITHUB_REF") != "refs/heads/main" or os.environ.get("PIPELINE_STATE_NAMESPACE") != "production":
        raise StateError("Reparo permitido somente em main/production")
    credentials = Credentials.from_authorized_user_info(json.loads(os.environ["YOUTUBE_TOKEN_ES"]))
    reconcile(Path(__file__).resolve().parent.parent,
              build("youtube", "v3", credentials=credentials, cache_discovery=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Reconciliação não concluída; conferir estado e evidência. Nenhum reenvio autorizado.") from None
