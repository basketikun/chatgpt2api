"""Mojeek Search API — independent crawler, UK-based.

Free tier available. Requires MOJEEK_API_KEY env var.
Mojeek has its own independent index (not Google/Bing), ~6 billion pages.
Strong on UK/European content — fills the regional search gap.
"""

from __future__ import annotations

import logging, os
from typing import Any
import httpx

logger = logging.getLogger(__name__)

MOJEEK_URL = "https://api.mojeek.com/search"


def mojeek_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    api_key = os.environ.get("MOJEEK_API_KEY", "")
    if not api_key:
        try:
            from src.sources_config import get_api_key
            api_key = get_api_key("mojeek")
        except Exception:
            pass
    if not api_key:
        return []

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                MOJEEK_URL,
                headers={"Accept": "application/json"},
                params={"q": query, "api_key": api_key, "results": min(limit, 10)},
            )
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Mojeek search failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for w in (data.get("results") or [])[:limit]:
        results.append({
            "title": w.get("title", ""),
            "snippet": (w.get("desc") or w.get("description") or "")[:400],
            "url": w.get("url", ""),
            "source": "Mojeek (UK)",
        })
    logger.info("Mojeek: %d results", len(results))
    return results
