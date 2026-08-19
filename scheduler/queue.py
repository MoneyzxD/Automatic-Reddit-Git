"""
scheduler/queue.py
==================
Gerencia filas de upload por idioma.

Cada idioma tem seu proprio arquivo de fila:
    data/queue/pt-br.json
    data/queue/en.json
    data/queue/es.json

Interface publica:
    enqueue()              — adiciona item na fila
    get_pending()          — retorna itens prontos para upload YouTube
    get_pending_tiktok()   — retorna itens onde TikTok ainda esta pendente
    update_status()        — atualiza status de um item
    count_uploads_today()  — conta uploads ja feitos hoje
    get_last_upload_time() — retorna datetime do ultimo upload
    mark_for_deletion()    — marca video local para deletar apos upload
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

STATUS = Literal["pending", "uploading", "uploaded", "partial", "failed", "cancelled"]

# Caminhos possiveis para a pasta de filas
_QUEUE_DIR_PATHS = [
    Path("data/queue"),
    Path("../data/queue"),
    Path(__file__).parent.parent / "data" / "queue",
]


def _find_queue_dir() -> Path:
    """Localiza ou cria a pasta de filas."""
    for path in _QUEUE_DIR_PATHS:
        if path.exists():
            return path
    queue_dir = _QUEUE_DIR_PATHS[0]
    queue_dir.mkdir(parents=True, exist_ok=True)
    return queue_dir


def _queue_path(language: str) -> Path:
    return _find_queue_dir() / f"{language}.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ── LEITURA E ESCRITA DA FILA ─────────────────────────────────────────────────

def _load_queue(language: str) -> dict:
    path = _queue_path(language)
    if not path.exists():
        return _empty_queue(language)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error("Erro ao carregar fila %s: %s", language, e)
        return _empty_queue(language)


def _save_queue(language: str, data: dict) -> None:
    path = _queue_path(language)
    path.parent.mkdir(parents=True, exist_ok=True)
    data["last_updated"] = _now_iso()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error("Erro ao salvar fila %s: %s", language, e)


def _empty_queue(language: str) -> dict:
    return {
        "language":       language,
        "last_updated":   _now_iso(),
        "uploads_today":  0,
        "last_upload_at": None,
        "items":          [],
    }


# ── INTERFACE PUBLICA ─────────────────────────────────────────────────────────

def enqueue(
    language: str,
    video_path: Path,
    thumbnail_path: Path | None,
    metadata: dict,
    title: str,
    planned_at: str | None = None,
    story_id: str = "",
    part: int = 1,
    total: int = 1,
) -> str:
    """
    Adiciona um item na fila de upload.
    Retorna o ID do item criado.

    story_id: identificador real da historia (ID do post do Reddit em
        producao, ou o ID fixo da historia de teste) — base preferida do ID
        do item, em vez do nome do arquivo. O nome do arquivo vem de um
        titulo gerado por LLM (via slugify), que pode colidir entre
        historias diferentes ou, em teste, e sempre o mesmo. Sem story_id,
        cai de volta pro nome do arquivo (compatibilidade).

        Em qualquer caso, uma colisao NUNCA descarta o item em silencio —
        um sufixo "_v2", "_v3"... e adicionado ate achar um ID livre.
    """
    queue = _load_queue(language)

    if story_id:
        sufixo  = f"_pt{part}of{total}" if total > 1 else ""
        base_id = f"{story_id}_{language}{sufixo}"
    else:
        base_id = Path(video_path).stem

    existing_ids = {item["id"] for item in queue["items"]}
    item_id   = base_id
    contador  = 2
    while item_id in existing_ids:
        item_id = f"{base_id}_v{contador}"
        contador += 1
    if item_id != base_id:
        logger.warning("ID '%s' ja existia na fila — criando entrada nova como '%s'",
                        base_id, item_id)

    item = {
        "id":             item_id,
        "status":         "pending",
        "video_path":     str(video_path),
        "thumbnail_path": str(thumbnail_path) if thumbnail_path else None,
        "metadata":       metadata,
        "schedule": {
            "planned_at":  planned_at or _now_iso(),
            "uploaded_at": None,
        },
        "platforms": {
            "youtube": {"status": "pending", "video_id": None, "url": None},
            "tiktok":  {"status": "pending", "video_id": None, "url": None},
        },
        "attempts":   0,
        "created_at": _now_iso(),
    }

    queue["items"].append(item)
    _save_queue(language, queue)
    logger.info("Item enfileirado: %s (%s)", item_id, language)
    return item_id


def get_pending(language: str) -> list[dict]:
    """
    Retorna lista de itens com status geral 'pending' na fila.
    Usado pelo upload_job do YouTube.
    Ordenados por planned_at (mais antigos primeiro).
    """
    queue   = _load_queue(language)
    pending = [
        item for item in queue["items"]
        if item["status"] == "pending"
        and Path(item.get("video_path", "")).exists()
    ]
    pending.sort(key=lambda x: x["schedule"].get("planned_at", ""))
    return pending


def get_pending_tiktok(language: str) -> list[dict]:
    """
    Retorna itens onde a plataforma TikTok ainda esta com status 'pending'.
    Independente do status geral do item (pode ser partial, uploaded, etc).
    Usado pelo tiktok_notify_job do runner.
    Ordenados por planned_at (mais antigos primeiro).
    """
    queue   = _load_queue(language)
    pending = [
        item for item in queue["items"]
        if item.get("platforms", {}).get("tiktok", {}).get("status") == "pending"
        and Path(item.get("video_path", "")).exists()
    ]
    pending.sort(key=lambda x: x["schedule"].get("planned_at", ""))
    return pending


def get_failed(language: str, max_attempts: int = 3) -> list[dict]:
    """
    Retorna itens com status 'failed' que ainda tem tentativas restantes.
    """
    queue = _load_queue(language)
    return [
        item for item in queue["items"]
        if item["status"] == "failed"
        and item.get("attempts", 0) < max_attempts
    ]


def update_status(
    language: str,
    item_id: str,
    platform: str,
    status: STATUS,
    video_id: str | None = None,
    url: str | None = None,
) -> None:
    """
    Atualiza o status de um item em uma plataforma especifica.
    Recalcula o status geral do item baseado nas plataformas.
    """
    queue = _load_queue(language)
    for item in queue["items"]:
        if item["id"] != item_id:
            continue

        if platform in item["platforms"]:
            item["platforms"][platform]["status"]   = status
            item["platforms"][platform]["video_id"] = video_id
            item["platforms"][platform]["url"]      = url

        statuses = [p["status"] for p in item["platforms"].values()]
        if all(s == "uploaded" for s in statuses):
            item["status"]                   = "uploaded"
            item["schedule"]["uploaded_at"]  = _now_iso()
            queue["last_upload_at"]          = _now_iso()
            queue["uploads_today"] = count_uploads_today(language) + 1
            logger.info("Upload completo: %s", item_id)
        elif any(s == "uploaded" for s in statuses):
            item["status"] = "partial"
            logger.warning("Upload parcial: %s", item_id)
        elif all(s == "failed" for s in statuses):
            item["status"] = "failed"
            item["attempts"] = item.get("attempts", 0) + 1
            logger.error("Upload falhou: %s (tentativa %d)", item_id, item["attempts"])
        elif any(s == "uploading" for s in statuses):
            item["status"] = "uploading"

        break

    _save_queue(language, queue)


def increment_attempts(language: str, item_id: str) -> int:
    """Incrementa contador de tentativas de um item. Retorna novo valor."""
    queue = _load_queue(language)
    for item in queue["items"]:
        if item["id"] == item_id:
            item["attempts"] = item.get("attempts", 0) + 1
            _save_queue(language, queue)
            return item["attempts"]
    return 0


def count_uploads_today(language: str) -> int:
    """
    Conta uploads realizados hoje.
    Reconstroi a partir dos itens para garantir precisao.
    """
    queue = _load_queue(language)
    today = _today_str()

    count = 0
    for item in queue["items"]:
        uploaded_at = item["schedule"].get("uploaded_at")
        if uploaded_at and uploaded_at.startswith(today):
            count += 1

    queue["uploads_today"] = count
    _save_queue(language, queue)
    return count


def get_last_upload_time(language: str) -> datetime | None:
    """
    Retorna datetime do ultimo upload confirmado.
    Retorna None se nunca houve upload.
    """
    queue    = _load_queue(language)
    last_str = queue.get("last_upload_at")
    if not last_str:
        return None
    try:
        return datetime.fromisoformat(last_str)
    except Exception:
        return None


def mark_for_deletion(language: str, item_id: str) -> None:
    """
    Remove video_path do item apos upload confirmado.
    O arquivo fisico e deletado pelo uploader — aqui apenas limpa o path.
    """
    queue = _load_queue(language)
    for item in queue["items"]:
        if item["id"] == item_id:
            item["video_path"]     = None
            item["thumbnail_path"] = None
            break
    _save_queue(language, queue)


def reset_daily_counter(language: str) -> None:
    """
    Reseta o contador diario de uploads.
    Limpa uploaded_at dos itens de hoje para que a recontagem funcione corretamente.
    """
    queue = _load_queue(language)
    today = _today_str()

    for item in queue["items"]:
        uploaded_at = item["schedule"].get("uploaded_at")
        if uploaded_at and uploaded_at.startswith(today):
            item["schedule"]["uploaded_at"] = None

    queue["uploads_today"] = 0
    _save_queue(language, queue)
    logger.info("Contador diario resetado: %s", language)


def get_queue_summary(language: str) -> dict:
    """Retorna resumo do estado atual da fila para logs e monitoramento."""
    queue  = _load_queue(language)
    items  = queue["items"]
    counts = {"pending": 0, "uploading": 0, "uploaded": 0,
              "partial": 0, "failed": 0, "cancelled": 0}
    for item in items:
        status = item.get("status", "pending")
        counts[status] = counts.get(status, 0) + 1
    return {
        "language":       language,
        "total":          len(items),
        "uploads_today":  count_uploads_today(language),
        "last_upload_at": queue.get("last_upload_at"),
        "by_status":      counts,
    }