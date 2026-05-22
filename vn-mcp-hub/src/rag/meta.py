"""Collection metadata — timestamp, update interval, auto-update config.

Each RAG collection can have a meta.json alongside its data/ folder.

Stored in data/<collection>/meta.json, read at query time to:
- Attach "last updated" timestamps to RAG results
- Decide if data is stale (needs refresh prompt)
- Drive the background auto-update scheduler
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")

# Default intervals in hours — per collection type
DEFAULT_INTERVALS = {
    # KB RAG collections: stable knowledge, update rarely
    "dien_nuoc": 720, "y_te": 720, "giao_duc": 720, "ngoai_ngu": 720,
    "khoa_hoc": 720, "tu_nhien": 720, "xa_hoi": 720, "sach": 720,
    # Dynamic/studio collections: shorter
    "_default": 168,
}


def _meta_path(collection: str) -> Path:
    return DATA_DIR / collection / "meta.json"


def read_meta(collection: str) -> dict:
    """Read collection metadata. Returns defaults if file doesn't exist."""
    path = _meta_path(collection)
    if not path.exists():
        interval = DEFAULT_INTERVALS.get(collection, DEFAULT_INTERVALS["_default"])
        return {
            "last_updated": None,
            "update_interval_hours": interval,
            "auto_update": False,
            "chunks_count": 0,
            "sources": [],
        }
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def write_meta(collection: str, data: dict) -> None:
    path = _meta_path(collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def touch(collection: str, chunks: int = 0, source: str = "") -> dict:
    """Update last_updated timestamp after an ingest or auto-update."""
    meta = read_meta(collection)
    meta["last_updated"] = datetime.now(timezone.utc).isoformat()
    if chunks > 0:
        meta["chunks_count"] = chunks
    if source and source not in meta.get("sources", []):
        sources = meta.get("sources") or []
        sources.append(source)
        meta["sources"] = sources
    write_meta(collection, meta)
    logger.info("Meta updated: %s (%d chunks, source=%s)", collection, chunks, source)
    return meta


def is_stale(collection: str) -> tuple[bool, str]:
    """Check if collection data is older than the user's update interval.

    Returns (stale: bool, message: str).
    """
    meta = read_meta(collection)
    last = meta.get("last_updated")
    if not last:
        return True, "Chưa có dữ liệu."

    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return True, "Dữ liệu timestamp lỗi."

    interval = meta.get("update_interval_hours", 168)
    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600

    if age_hours > interval:
        days = int(age_hours / 24)
        if days > 0:
            return True, f"Dữ liệu đã {days} ngày (cập nhật lần cuối: {last_dt.strftime('%d/%m/%Y')})."
        hours = int(age_hours)
        return True, f"Dữ liệu đã {hours} giờ (cập nhật lần cuối: {last_dt.strftime('%H:%M %d/%m/%Y')})."

    return False, ""


def get_age_str(collection: str) -> str:
    """Human-readable age string for the last update."""
    meta = read_meta(collection)
    last = meta.get("last_updated")
    if not last:
        return "Chưa cập nhật"
    try:
        last_dt = datetime.fromisoformat(last)
        delta = datetime.now(timezone.utc) - last_dt
        hours = delta.total_seconds() / 3600
        if hours < 1:
            return f"{int(hours * 60)} phút trước"
        if hours < 24:
            return f"{int(hours)} giờ trước"
        return f"{int(hours / 24)} ngày trước"
    except Exception:
        return "Không rõ"
