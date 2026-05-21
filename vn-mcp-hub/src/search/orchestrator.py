"""Federated search orchestrator — queries multiple backends in parallel.

Called by hybrid.py when RAG results are insufficient. Queries 5-10+
international search engines simultaneously via ThreadPoolExecutor.

Each backend is a (module_path, function_name) tuple. Backends that fail
(no key, network error, timeout) are silently skipped — the orchestrator
returns whatever succeeds.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

logger = logging.getLogger(__name__)

# Pre-resolve known hostnames in main thread (Docker DNS fails in worker threads)
import src.dns_cache as _dns  # noqa

# Backend registry: (module, fn_name). Each fn takes (query, limit) -> list[dict].
SEARCH_BACKENDS = [
    # Web search — general purpose
    ("src.vn.search", "ddg_search"),                    # DuckDuckGo (global)
    ("src.general.wikipedia", "wiki_search"),            # Wikipedia
    ("src.search.brave", "brave_search"),               # Brave (US, independent)
    # Academic / scholarly
    ("src.search.semantic_scholar", "semantic_scholar_search"),  # CS/engineering
    ("src.search.crossref", "crossref_search"),                   # DOI registry
    ("src.search.pubmed", "pubmed_search"),                       # Biomedical (NIH)
    ("src.search.openalex", "openalex_search"),                   # 250M works
    # Historical / archival
    ("src.search.internet_archive", "archive_search"),            # Wayback Machine
]

MAX_WORKERS = 9
PER_BACKEND_TIMEOUT = 15.0


def _call_one_backend(module_path: str, fn_name: str, query: str, limit: int) -> list[dict[str, Any]]:
    """Import and call a single backend's direct search function."""
    try:
        module = __import__(module_path, fromlist=[fn_name])
        fn = getattr(module, fn_name, None)
        if fn is None:
            return []
        return fn(query, limit)
    except Exception as exc:
        logger.debug("Backend %s.%s skipped: %s", module_path, fn_name, exc)
        return []


def federated_search(query: str, limit_per_source: int = 3) -> list[dict[str, Any]]:
    """Query all search backends in parallel.

    Returns flat list of {title, snippet, url, source} dicts.
    Results are deduplicated by URL.
    """
    # Pre-resolve DNS in main thread (Docker DNS fails in worker threads)
    try:
        import src.dns_cache
        src.dns_cache.pre_resolve()
        import time; time.sleep(0.3)  # Let DNS resolutions settle
    except Exception:
        pass

    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_call_one_backend, path, fn, query, limit_per_source): (path, fn)
            for path, fn in SEARCH_BACKENDS
        }
        for future in as_completed(futures, timeout=PER_BACKEND_TIMEOUT * 2):
            path, fn = futures[future]
            try:
                hits = future.result(timeout=PER_BACKEND_TIMEOUT)
                results.extend(hits)
            except Exception as exc:
                logger.debug("Backend %s.%s timed out: %s", path, fn, exc)

    # Deduplicate by URL
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in results:
        url = r.get("url") or ""
        if url and url in seen:
            continue
        seen.add(url)
        deduped.append(r)

    logger.info("Federated search: %d results (%d unique) for '%s'",
                len(results), len(deduped), query[:60])
    return deduped


def format_federated_results(results: list[dict[str, Any]]) -> str:
    """Format federated results into markdown grouped by source."""
    if not results:
        return "Không tìm thấy kết quả từ bất kỳ nguồn quốc tế nào."

    grouped: dict[str, list[dict]] = defaultdict(list)
    for h in results:
        grouped[h.get("source", "Web")].append(h)

    lines = [f"## Tìm kiếm quốc tế ({len(results)} kết quả từ {len(grouped)} nguồn)\n"]
    for source, hits in sorted(grouped.items()):
        lines.append(f"### {source} ({len(hits)})")
        for i, h in enumerate(hits, 1):
            title = h.get("title") or ""
            snippet = (h.get("snippet") or "")[:300]
            url = h.get("url") or ""
            year = h.get("year") or ""
            meta = f" ({year})" if year else ""
            lines.append(f"{i}. **{title}**{meta}")
            if snippet:
                lines.append(f"   {snippet}")
            if url:
                lines.append(f"   {url}")
        lines.append("")
    return "\n".join(lines)
