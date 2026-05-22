"""PubMed Entrez — biomedical/life sciences literature (NIH, US).

Free, no API key required. The standard for medical literature search
worldwide. Used by doctors, researchers, and the WHO.
"""

from __future__ import annotations

import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

PUBMED_SEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_SUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def pubmed_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=12.0) as client:
            # Step 1: search for IDs
            r = client.get(PUBMED_SEARCH, params={
                "db": "pubmed", "term": query, "retmax": min(limit, 10),
                "retmode": "json", "sort": "relevance",
            })
            r.raise_for_status()
            ids = r.json().get("esearchresult", {}).get("idlist") or []
            if not ids:
                return []

            # Step 2: get summaries
            r2 = client.get(PUBMED_SUMMARY, params={
                "db": "pubmed", "id": ",".join(ids[:limit]), "retmode": "json",
            })
            r2.raise_for_status()
            data = r2.json()
    except Exception as exc:
        logger.warning("PubMed search failed: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    for pid in ids[:limit]:
        info = (data.get("result") or {}).get(pid) or {}
        title = info.get("title", "")
        pub_date = info.get("pubdate", "")
        source = info.get("source", "")
        authors = (info.get("authors") or [])[:3]
        author_str = ", ".join(a.get("name", "") for a in authors) if authors else ""
        doi = ""
        for aid in info.get("articleids") or []:
            if aid.get("idtype") == "doi":
                doi = aid.get("value", "")
                break

        snippet_parts = []
        if pub_date:
            snippet_parts.append(f"({pub_date})")
        if author_str:
            snippet_parts.append(author_str)
        if source:
            snippet_parts.append(f"[{source}]")
        snippet = " ".join(snippet_parts)

        results.append({
            "title": title,
            "snippet": snippet,
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pid}/" if not doi else f"https://doi.org/{doi}",
            "source": "PubMed (NIH)",
            "year": pub_date[:4] if pub_date else "",
        })
    logger.info("PubMed: %d results", len(results))
    return results
