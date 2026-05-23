"""Collection metadata — timestamp, update interval, auto-update config.

Each RAG collection can have a meta.json alongside its data/ folder.

Stored in data/<collection>/meta.json, read at query time to:
- Attach "last updated" timestamps to RAG results
- Decide if data is stale (needs refresh prompt)
- Drive the background auto-update scheduler

Stale model (matches user request):

    < soft_notify_days (60d)   →  fresh           — no action
    >= soft_notify_days        →  aging           — suggest user manual refresh
    >= update_interval_hours   →  stale           — background scheduler auto-refreshes

Defaults (KB collections like dien_nuoc / y_te / xa_hoi):
    soft_notify_days       = 60   (≈ 2 months)
    update_interval_hours  = 2160 (≈ 90 days, 3 months)

Both can be overridden per-collection in meta.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

DATA_DIR = Path("/app/data")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except (TypeError, ValueError):
        return default


# Default interval (hours) before background auto-refresh kicks in.
# 2160 h = 90 days = 3 months — domain KBs change slowly so this is the
# sweet spot between fresh data and not burning codex on background tasks.
_DEFAULT_KB_INTERVAL_H = _env_int("RAG_DEFAULT_INTERVAL_HOURS", 2160)
# Default interval for non-KB collections (studio-created, dynamic content).
_DEFAULT_OTHER_INTERVAL_H = _env_int("RAG_DEFAULT_INTERVAL_HOURS_OTHER", 720)
# Number of days after which we add a "you might want to refresh this"
# notice to RAG results, so the user can trigger a refresh before the
# background scheduler fires.
_DEFAULT_SOFT_NOTIFY_DAYS = _env_int("RAG_SOFT_NOTIFY_DAYS", 60)

# Default intervals in hours — per collection type
DEFAULT_INTERVALS = {
    # KB RAG collections — stable knowledge, refresh every 3 months
    "dien_nuoc": _DEFAULT_KB_INTERVAL_H, "y_te": _DEFAULT_KB_INTERVAL_H,
    "giao_duc":  _DEFAULT_KB_INTERVAL_H, "ngoai_ngu": _DEFAULT_KB_INTERVAL_H,
    "khoa_hoc":  _DEFAULT_KB_INTERVAL_H, "tu_nhien":  _DEFAULT_KB_INTERVAL_H,
    "xa_hoi":    _DEFAULT_KB_INTERVAL_H, "sach":      _DEFAULT_KB_INTERVAL_H,
    # Dynamic / studio-created collections — refresh monthly
    "_default":  _DEFAULT_OTHER_INTERVAL_H,
}


def _meta_path(collection: str) -> Path:
    return DATA_DIR / collection / "meta.json"


def _global_defaults() -> tuple[int, int]:
    """Read the per-install defaults the user set in the Studio UI.
    Falls back to module constants if settings can't be loaded."""
    try:
        from src.rag.settings import (
            get_default_refresh_interval_hours,
            get_default_soft_notify_days,
        )
        return get_default_refresh_interval_hours(), get_default_soft_notify_days()
    except Exception:
        return _DEFAULT_KB_INTERVAL_H, _DEFAULT_SOFT_NOTIFY_DAYS


def read_meta(collection: str) -> dict:
    """Read collection metadata. Returns defaults if file doesn't exist.

    Precedence for refresh-related fields:
        meta.json (per-collection)  >  studio settings  >  env  >  hardcoded
    """
    g_interval, g_soft = _global_defaults()
    interval_default = DEFAULT_INTERVALS.get(collection, g_interval)
    path = _meta_path(collection)
    if not path.exists():
        return {
            "last_updated": None,
            "update_interval_hours": interval_default,
            "soft_notify_days": g_soft,
            "auto_update": False,
            "chunks_count": 0,
            "sources": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    # Backfill defaults if older meta.json files are missing newer fields.
    data.setdefault("soft_notify_days", g_soft)
    data.setdefault("update_interval_hours", interval_default)
    return data


def write_meta(collection: str, data: dict) -> None:
    path = _meta_path(collection)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def touch(collection: str, chunks: int = 0, source: str = "") -> dict:
    """Update last_updated timestamp after an ingest or auto-update.

    This is what resets the refresh timer — both for soft (notify) and
    hard (auto-refresh) thresholds.
    """
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

    "Stale" here is the HARD threshold — the background scheduler should
    refresh now. For the softer "consider refreshing" hint use get_status().

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

    interval = meta.get("update_interval_hours", DEFAULT_INTERVALS["_default"])
    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600

    if age_hours > interval:
        days = int(age_hours / 24)
        if days > 0:
            return True, f"Dữ liệu đã {days} ngày (cập nhật lần cuối: {last_dt.strftime('%d/%m/%Y')})."
        hours = int(age_hours)
        return True, f"Dữ liệu đã {hours} giờ (cập nhật lần cuối: {last_dt.strftime('%H:%M %d/%m/%Y')})."

    return False, ""


def get_status(collection: str) -> dict:
    """Structured freshness status for one collection.

    Returns:
        {
          "collection":           "xa_hoi",
          "last_updated":         "2026-03-15T10:00:00+00:00"  | None,
          "last_updated_str":     "15/03/2026"                 | "chưa có",
          "age_days":             45                           | None,
          "interval_days":        90,
          "soft_notify_days":     60,
          "status":               "missing" | "fresh" | "aging" | "stale",
          "should_suggest_refresh": bool,    # aging or stale
          "should_auto_refresh":    bool,    # stale
        }
    """
    meta = read_meta(collection)
    last = meta.get("last_updated")
    interval_h = int(meta.get("update_interval_hours") or DEFAULT_INTERVALS["_default"])
    soft_days = int(meta.get("soft_notify_days") or _DEFAULT_SOFT_NOTIFY_DAYS)
    interval_days = max(1, interval_h // 24)

    base = {
        "collection": collection,
        "last_updated": last,
        "interval_days": interval_days,
        "soft_notify_days": soft_days,
    }

    if not last:
        return {
            **base,
            "last_updated_str": "chưa có",
            "age_days": None,
            "status": "missing",
            "should_suggest_refresh": True,
            "should_auto_refresh": True,
        }

    try:
        last_dt = datetime.fromisoformat(last)
    except Exception:
        return {
            **base,
            "last_updated_str": "lỗi",
            "age_days": None,
            "status": "missing",
            "should_suggest_refresh": True,
            "should_auto_refresh": True,
        }

    age_h = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
    age_days = int(age_h // 24)

    if age_h >= interval_h:
        status = "stale"
    elif age_days >= soft_days:
        status = "aging"
    else:
        status = "fresh"

    return {
        **base,
        "last_updated_str": last_dt.strftime("%d/%m/%Y"),
        "age_days": age_days,
        "status": status,
        "should_suggest_refresh": status in ("aging", "stale"),
        "should_auto_refresh": status == "stale",
    }


def render_refresh_hint(collection: str, status: dict | None = None) -> str:
    """Human-readable "you might want to refresh this" notice to append
    to RAG responses. Empty string when no notice is needed."""
    s = status or get_status(collection)
    if not s.get("should_suggest_refresh"):
        return ""
    if s["status"] == "stale":
        return (
            f"\n\n🔄 _Kiến thức `{collection}` đã {s['age_days']} ngày "
            f"(cập nhật cuối {s['last_updated_str']}, đã quá kỳ "
            f"{s['interval_days']} ngày). Sẽ tự động làm mới ở lần check tiếp theo. "
            f"Nếu muốn ngay, gọi `/api/rag/refresh/{collection}` trên vn-mcp-hub._"
        )
    if s["status"] == "aging":
        return (
            f"\n\n💡 _Kiến thức `{collection}` đã {s['age_days']} ngày "
            f"(cập nhật cuối {s['last_updated_str']}). Sẽ tự làm mới sau "
            f"{s['interval_days'] - s['age_days']} ngày nữa. "
            f"Nếu cần cập nhật ngay, gọi `/api/rag/refresh/{collection}`._"
        )
    return ""


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
