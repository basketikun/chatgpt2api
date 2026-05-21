"""Semantic Scholar — academic paper search (CS, engineering, medicine).

Free, no API key required. Rate limited to ~1 req/sec without key.
Covers 200M+ papers across all disciplines.
"""

from __future__ import annotations

import logging, time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SS_API = "https://api.semanticscholar.org/graph/v1/paper/search"
HEADERS = {"Accept": "application/json"}

# Simple in-memory cache to avoid 429 rate limits (1 req/s without API key)
_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL = 60  # seconds


def semantic_scholar_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Search Semantic Scholar for academic papers.

    Returns list of {title, snippet, url, source, year, citations} dicts.
    Uses simple cache to stay within rate limits.
    """
    # Check cache
    cache_key = f"{query}:{limit}"
    if cache_key in _cache:
        ts, cached = _cache[cache_key]
        if time.time() - ts < _CACHE_TTL:
            return cached

    # Retrieve API key if available
    from src.sources_config import get_api_key
    api_key = get_api_key("semantic_scholar")
    headers = dict(HEADERS)
    if api_key:
        headers["x-api-key"] = api_key

    data = {}
    for attempt in range(3):
        try:
            with httpx.Client(timeout=10.0, headers=headers) as client:
                r = client.get(
                    SS_API,
                    params={
                        "query": query,
                        "limit": min(limit, 10),
                        "fields": "title,year,abstract,citationCount,url",
                    },
                )
                r.raise_for_status()
                data = r.json()
            break
        except Exception as exc:
            if attempt < 2 and ("429" in str(exc) or "too many requests" in str(exc).lower()):
                sleep_time = (attempt + 1) * 2
                logger.info("Semantic Scholar rate limited (429). Retrying in %d seconds...", sleep_time)
                time.sleep(sleep_time)
                continue
            logger.warning("Semantic Scholar search failed: %s", exc)
            return []

    results: list[dict[str, Any]] = []
    for paper in (data.get("data") or [])[:limit]:
        title = paper.get("title") or ""
        abstract = paper.get("abstract") or ""
        year = paper.get("year") or ""
        citations = paper.get("citationCount") or 0
        url = paper.get("url") or f"https://api.semanticscholar.org/paper/{paper.get('paperId','')}"
        snippet = abstract[:400] if abstract else ""
        if year:
            snippet = f"({year}, {citations} citations) {snippet}"
        results.append({
            "title": title,
            "snippet": snippet.strip(),
            "url": url,
            "source": "Semantic Scholar",
            "year": year,
            "citations": citations,
        })
    logger.info("Semantic Scholar: %d results for '%s'", len(results), query[:50])
    # Save to cache
    _cache[cache_key] = (time.time(), results)
    # Clean old entries periodically
    if len(_cache) > 100:
        now = time.time()
        _cache.clear()  # simple: clear all when too many
    return results
