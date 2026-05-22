"""Hybrid RAG + web search fallback for kb_* MCPs.

When the local knowledge base (Chroma) returns empty or low-quality results,
this module falls back to DuckDuckGo and Wikipedia so the LLM always gets
something useful — no LLM-merge, just raw text from both sources.

Usage in kb_* tools:
    results = hybrid_query(COLLECTION, question, top_k)
    return format_hybrid_results(results)
"""

from __future__ import annotations

import logging
from typing import Any

from src.rag.retriever import RAGRetriever, DEFAULT_TOP_K

logger = logging.getLogger(__name__)

# If RAG returns fewer chunks than this, we fall back to web search.
MIN_RAG_CHUNKS = 2


def hybrid_query(collection: str, text: str, top_k: int = DEFAULT_TOP_K, force_refresh: bool = False) -> dict[str, Any]:
    """Query RAG + optional web search fallback.

    Args:
        force_refresh: If True, skip RAG entirely and search web only.

    Returns:
        {"rag": [...], "web": [...], "total": int, "stale": bool, "stale_msg": str,
         "last_updated": str|None}
    """
    retriever = RAGRetriever.get()

    rag_results: list[dict[str, Any]] = []
    if not force_refresh:
        rag_results = retriever.query(collection, text, top_k)

    # Check staleness
    stale = False
    stale_msg = ""
    last_updated = None
    try:
        from src.rag.meta import is_stale as _stale
        stale, stale_msg = _stale(collection)
        from src.rag.meta import read_meta
        last_updated = read_meta(collection).get("last_updated")
    except Exception:
        pass

    # Decide whether to fall back to web search
    need_web = _should_search_web(retriever, collection, rag_results) or force_refresh

    web_results: list[dict[str, Any]] = []
    if need_web:
        web_results = _fallback_search(text)
        logger.info("Hybrid(%s): RAG=%d, web=%d, stale=%s", collection, len(rag_results), len(web_results), stale)

    return {
        "rag": rag_results,
        "web": web_results,
        "total": len(rag_results) + len(web_results),
        "stale": stale,
        "stale_msg": stale_msg,
        "last_updated": last_updated,
    }


def _should_search_web(retriever: RAGRetriever, collection: str, rag: list[dict[str, Any]]) -> bool:
    """True if RAG is insufficient and we should try web search.

    Only searches when RAG is completely empty — no more score-based triggers.
    Auto-search runs in the scheduler, not on every user query.
    """
    stats = retriever.collection_stats(collection)
    if not stats.get("available") or stats.get("count", 0) == 0:
        return True
    if len(rag) == 0:
        return True
    return False


def _fallback_search(query: str) -> list[dict[str, Any]]:
    """Run DuckDuckGo + Wikipedia search in parallel.

    Returns up to 10 results total (5 DDG + 5 Wiki), each as {title, snippet, url, source}.
    """
    search_results: list[dict[str, Any]] = []
    try:
        from src.search.orchestrator import federated_search as _fs
        search_results = _fs(query, limit_per_source=3)
    except Exception as exc:
        logger.warning("Hybrid: federated search fallback failed: %s", exc)

    return search_results


def format_hybrid_results(result: dict[str, Any]) -> str:
    """Format hybrid query results into a markdown block for the LLM."""
    if result["total"] == 0:
        return "Không tìm thấy thông tin liên quan trong kho tri thức hay trên web."

    parts: list[str] = []

    # Stale warning
    if result.get("stale"):
        parts.append(f"⚠️ {result.get('stale_msg', 'Dữ liệu có thể đã cũ.')}")

    rag = result.get("rag") or []
    if rag:
        from src.rag.retriever import format_results
        header = "## Kho tri thức"
        if result.get("last_updated"):
            header += f" (cập nhật: {result['last_updated'][:10]})"
        parts.append(f"{header} ({len(rag)} kết quả)\n\n{format_results(rag)}")

    web = result.get("web") or []
    if web:
        from src.search.orchestrator import format_federated_results
        parts.append(format_federated_results(web))
    elif rag:
        # RAG hit, no web search — prompt user if they want fresh results
        parts.append("---\n💡 *Dữ liệu từ kho tri thức. Bạn có muốn tôi tìm thêm thông tin mới nhất từ web không?*")

    if result.get("stale") and rag:
        parts.append("🔄 *Dữ liệu có thể đã cũ. Auto-update sẽ chạy theo lịch, hoặc bạn có thể yêu cầu tôi tìm ngay.*")

    return "\n\n".join(parts)
