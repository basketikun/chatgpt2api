"""vn_search — tìm web qua DuckDuckGo HTML scrape.

DuckDuckGo's html endpoint (`html.duckduckgo.com/html/`) returns rendered
HTML for any query without requiring an API key. We parse the result list
and return clean snippets — handles Vietnamese queries fine.

Tools:
- search_web(query, limit=10): tìm chung
- search_news(query, limit=10): tìm tin tức (kiểu DDG news)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_search")

DDG_HTML = "https://html.duckduckgo.com/html/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def _parse_results(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, Any]] = []
    for div in soup.select("div.result"):
        a = div.select_one("a.result__a")
        snippet_el = div.select_one("a.result__snippet") or div.select_one(".result__snippet")
        if not a:
            continue
        title = a.get_text(strip=True)
        link = a.get("href") or ""
        snippet = snippet_el.get_text(" ", strip=True) if snippet_el else ""
        if not title or not link:
            continue
        results.append({"title": title, "link": link, "url": link, "snippet": snippet})
    return results


def _format(results: list[dict[str, Any]], limit: int) -> str:
    items = results[:limit]
    if not items:
        return "Không tìm thấy kết quả."
    lines = []
    for i, r in enumerate(items, 1):
        lines.append(
            f"{i}. **{r['title']}**\n"
            f"   {r['snippet']}\n"
            f"   {r['link']}"
        )
    return "\n\n".join(lines)


def ddg_search(query: str, limit: int = 5) -> list[dict[str, Any]]:
    """Direct DuckDuckGo search — reusable by hybrid RAG without MCP protocol.

    Returns list of {title, link, snippet, source} dicts, empty list on failure.
    """
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
            r = client.post(DDG_HTML, data={"q": query, "kl": "vn-vi"})
            r.raise_for_status()
        results = _parse_results(r.text)[:limit]
        for r in results:
            r["source"] = "DuckDuckGo"
        return results
    except Exception as exc:
        logger.warning("DDG search failed for '%s': %s", query, exc)
        return []


@mcp.tool()
def search_web(query: str, limit: int = 10) -> str:
    """Tìm web qua DuckDuckGo. Không cần API key, hỗ trợ tiếng Việt.

    Args:
        query: Truy vấn tìm kiếm (vd: "giá vàng hôm nay", "thời tiết Hà Nội").
        limit: Số kết quả tối đa (1-20, mặc định 10).

    Returns:
        Danh sách kết quả: tiêu đề, mô tả, link.
    """
    limit = max(1, min(20, limit))
    results = ddg_search(query, limit)
    if not results:
        return "Không tìm thấy kết quả."
    return _format(results, limit)


@mcp.tool()
def search_news(query: str, limit: int = 10) -> str:
    """Tìm tin tức qua DuckDuckGo (filter site là báo lớn VN).

    Args:
        query: Từ khóa tin tức.
        limit: Số bài tối đa (1-20, mặc định 10).

    Returns:
        Tin tức từ vnexpress.net, tuoitre.vn, thanhnien.vn, dantri.com.vn.
    """
    sites = "site:vnexpress.net OR site:tuoitre.vn OR site:thanhnien.vn OR site:dantri.com.vn"
    return search_web(f"{query} ({sites})", limit)
