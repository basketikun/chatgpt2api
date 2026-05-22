"""Internet Archive — historical web pages, texts, media (US).

Free, no API key. The Wayback Machine's search API. Provides access to
archived web content, books, and historical records — unique perspective
that other search engines can't offer.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

ARCHIVE_URL = "https://archive.org/advancedsearch.php"


def archive_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    for attempt in range(2):
        try:
            with httpx.Client(timeout=20.0) as client:
                r = client.get(ARCHIVE_URL, params={
                    "q": f"title:({query}) OR description:({query})",
                    "fl[]": "identifier,title,description,year,mediatype",
                    "rows": min(limit, 10),
                    "output": "json",
                })
                r.raise_for_status()
                data = r.json()
            break
        except Exception as exc:
            if attempt == 0:
                import time; time.sleep(1)
                continue
            logger.warning("Internet Archive search failed: %s", exc)
            return []

    results: list[dict[str, Any]] = []
    for doc in (data.get("response", {}).get("docs") or [])[:limit]:
        identifier = doc.get("identifier", "")
        title = doc.get("title", "")
        desc = (doc.get("description") or "")[:400]
        year = doc.get("year") or ""
        mediatype = doc.get("mediatype", "")

        snippet_parts = []
        if year:
            snippet_parts.append(f"({year})")
        if mediatype:
            snippet_parts.append(f"[{mediatype}]")
        if desc:
            snippet_parts.append(desc)
        snippet = " ".join(snippet_parts)

        results.append({
            "title": title,
            "snippet": snippet,
            "url": f"https://archive.org/details/{identifier}" if identifier else "",
            "source": "Internet Archive (US)",
            "year": str(year) if year else "",
        })
    logger.info("Internet Archive: %d results", len(results))
    return results
