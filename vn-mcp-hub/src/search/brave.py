"""Brave Search API — independent web index, privacy-focused (US).

Free tier: 2,000 queries/month. Requires BRAVE_API_KEY env var.
Covers general web with its own crawler, not Google/Bing dependent.
"""

from __future__ import annotations

import logging, os
from typing import Any
import httpx

logger = logging.getLogger(__name__)

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"


def brave_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    api_key = os.environ.get("BRAVE_API_KEY", "")
    if not api_key:
        try:
            from src.sources_config import get_api_key
            api_key = get_api_key("brave")
        except Exception:
            pass
    if not api_key:
        return []

    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(
                BRAVE_URL,
                headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                params={"q": query, "count": min(limit, 10)},
            )
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("Brave search failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    web = data.get("web", {}).get("results") or []
    for w in web[:limit]:
        results.append({
            "title": w.get("title", ""),
            "snippet": (w.get("description") or "")[:400],
            "url": w.get("url", ""),
            "source": "Brave (US)",
        })
    logger.info("Brave: %d results", len(results))
    return results
