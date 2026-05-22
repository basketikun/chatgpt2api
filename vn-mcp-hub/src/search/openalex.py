"""OpenAlex — open catalog of 250M+ scholarly works, free no key.

Indexes papers, authors, institutions, and topics across all disciplines.
The largest open-access scholarly database — alternatives to paywalled Scopus/WoS.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

OPENALEX_URL = "https://api.openalex.org/works"


def openalex_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(OPENALEX_URL, params={
                "search": query,
                "per_page": min(limit, 10),
                "sort": "cited_by_count:desc",
            })
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("OpenAlex search failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for w in (data.get("results") or [])[:limit]:
        title = w.get("title", "")
        pub_year = w.get("publication_year") or ""
        cited = w.get("cited_by_count") or 0
        doi = w.get("doi") or ""
        abstract = ""
        abstract_inverted = w.get("abstract_inverted_index")
        if abstract_inverted and isinstance(abstract_inverted, dict):
            try:
                words = sorted((pos, word) for word, positions in abstract_inverted.items() for pos in positions)
                abstract = " ".join(w for _, w in words)[:400]
            except Exception:
                pass

        snippet_parts = []
        if pub_year:
            snippet_parts.append(f"({pub_year})")
        if cited:
            snippet_parts.append(f"{cited} citations")
        if abstract:
            snippet_parts.append(abstract)
        snippet = " ".join(snippet_parts)

        results.append({
            "title": title or "",
            "snippet": snippet,
            "url": f"https://doi.org/{doi}" if doi else w.get("id", ""),
            "source": "OpenAlex",
            "year": str(pub_year) if pub_year else "",
            "citations": cited,
        })
    logger.info("OpenAlex: %d results", len(results))
    return results
