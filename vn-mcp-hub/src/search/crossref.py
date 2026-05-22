"""CrossRef — scholarly DOI metadata search.

Free, no API key required (polite pool). Covers journal articles, books,
conference proceedings, preprints, datasets. The infrastructure behind
DOI resolution for academic publishing.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

CROSSREF_API = "https://api.crossref.org/works"
HEADERS = {"Accept": "application/json"}


def crossref_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search CrossRef for scholarly works (articles, books, proceedings).

    Returns list of {title, snippet, url, source, year, publisher, type} dicts.
    Empty list on failure or no results.
    """
    try:
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            r = client.get(
                CROSSREF_API,
                params={
                    "query": query,
                    "rows": min(limit, 10),
                    "select": "DOI,title,abstract,published-print,container-title,publisher,type",
                },
            )
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("CrossRef search failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    items = data.get("message", {}).get("items") or []
    for item in items[:limit]:
        title_list = item.get("title") or []
        title = title_list[0] if title_list else ""
        abstract = (item.get("abstract") or "")[:400]
        doi = item.get("DOI") or ""
        year_info = item.get("published-print", {}).get("date-parts", [[None]])[0]
        year = str(year_info[0]) if year_info and year_info[0] else ""
        publisher = item.get("publisher", "")
        container = (item.get("container-title") or [""])[0]
        work_type = item.get("type", "")

        snippet_parts = []
        if year:
            snippet_parts.append(f"({year})")
        if publisher:
            snippet_parts.append(publisher)
        if container:
            snippet_parts.append(f"[{container}]")
        if abstract:
            snippet_parts.append(abstract)
        snippet = " ".join(snippet_parts)

        results.append({
            "title": title,
            "snippet": snippet,
            "url": f"https://doi.org/{doi}" if doi else "",
            "source": "CrossRef",
            "year": year,
            "publisher": publisher,
            "type": work_type,
        })
    logger.info("CrossRef: %d results for '%s'", len(results), query[:50])
    return results
