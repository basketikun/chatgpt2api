"""wikipedia — search và lấy nội dung Wikipedia đa ngôn ngữ.

Wraps the public Wikipedia REST API (vi.wikipedia.org, en.wikipedia.org, ...)
without auth. Default language is Vietnamese to match user audience.

Tools:
- search(query, lang, limit): tìm bài viết
- get_summary(title, lang): tóm tắt bài viết
- get_full_article(title, lang): full text
"""

from __future__ import annotations

import logging

from typing import Any

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("wikipedia")

WIKI_API = "https://{lang}.wikipedia.org/w/api.php"
WIKI_REST = "https://{lang}.wikipedia.org/api/rest_v1"

HEADERS = {"User-Agent": "vn-mcp-hub/0.1 (chatgpt2api integration)"}


def wiki_search(query: str, lang: str = "vi", limit: int = 5) -> list[dict[str, Any]]:
    """Direct Wikipedia search — reusable by hybrid RAG without MCP protocol.

    Returns list of {title, snippet, url} dicts, empty list on failure.
    Uses IP + Host header to bypass Docker thread DNS issues.
    """
    limit = max(1, min(30, limit))
    params = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
    }
    hostname = f"{lang}.wikipedia.org"
    # Resolve IP in this thread (works around Docker+AdGuard DNS failures in ThreadPoolExecutor)
    try:
        from src.dns_cache import get_ip
        ip = get_ip(hostname)
    except Exception:
        ip = hostname

    for attempt in range(2):
        try:
            headers = dict(HEADERS)
            if ip != hostname:
                headers["Host"] = hostname
                api_url = f"https://{ip}/w/api.php"
            else:
                api_url = WIKI_API.format(lang=lang)
            with httpx.Client(timeout=10.0, headers=headers, verify=(ip == hostname)) as client:
                r = client.get(api_url, params=params)
                r.raise_for_status()
            data = r.json()
            break
        except Exception as exc:
            if attempt == 0:
                import time; time.sleep(1)
                continue
            logger.warning("Wiki search failed for '%s': %s", query, exc)
            return []

    hits = (data.get("query") or {}).get("search") or []
    return [
        {
            "title": h.get("title", ""),
            "snippet": (h.get("snippet", "")
                        .replace('<span class="searchmatch">', "**")
                        .replace("</span>", "**")),
            "url": f"https://{lang}.wikipedia.org/wiki/{h.get('title', '').replace(' ', '_')}",
        }
        for h in hits
    ]


@mcp.tool()
def search(query: str, lang: str = "vi", limit: int = 10) -> str:
    """Tìm bài viết Wikipedia.

    Args:
        query: Từ khóa tìm kiếm.
        lang: Mã ngôn ngữ Wikipedia (mặc định 'vi'; có 'en', 'ja', 'zh', ...).
        limit: Số kết quả tối đa (mặc định 10).

    Returns:
        Danh sách bài viết khớp gồm tiêu đề + đoạn snippet + URL.
    """
    limit = max(1, min(30, limit))
    hits = wiki_search(query, lang, limit)
    if not hits:
        return f"Không tìm thấy bài viết nào cho '{query}' trên {lang}.wikipedia.org."
    lines = [f"**{len(hits)} bài Wikipedia ({lang}) khớp '{query}':**", ""]
    for i, h in enumerate(hits, 1):
        lines.append(f"{i}. **{h['title']}**\n   {h['snippet']}\n   {h['url']}")
    return "\n\n".join(lines)


@mcp.tool()
def get_summary(title: str, lang: str = "vi") -> str:
    """Lấy tóm tắt một bài viết Wikipedia.

    Args:
        title: Tên bài viết (vd: "Hà Nội", "Albert Einstein").
        lang: Mã ngôn ngữ Wikipedia (mặc định 'vi').

    Returns:
        Đoạn mở đầu của bài Wikipedia.
    """
    url = f"{WIKI_REST.format(lang=lang)}/page/summary/{title.replace(' ', '_')}"
    try:
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        return f"Không lấy được tóm tắt '{title}' ({lang}): {exc}"

    title_resolved = data.get("title", title)
    extract = data.get("extract", "")
    page_url = (data.get("content_urls") or {}).get("desktop", {}).get("page", "")
    if not extract:
        return f"Bài '{title_resolved}' không có tóm tắt khả dụng."
    return f"**{title_resolved}**\n\n{extract}\n\n_Nguồn: {page_url}_"


@mcp.tool()
def get_full_article(title: str, lang: str = "vi") -> str:
    """Lấy nội dung đầy đủ một bài viết Wikipedia (cắt 8000 ký tự nếu quá dài).

    Args:
        title: Tên bài viết.
        lang: Mã ngôn ngữ (mặc định 'vi').

    Returns:
        Toàn văn bài viết dạng plain text.
    """
    params = {
        "action": "query",
        "prop": "extracts",
        "explaintext": "true",
        "titles": title,
        "format": "json",
        "redirects": "true",
    }
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS) as client:
            r = client.get(WIKI_API.format(lang=lang), params=params)
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        return f"Không lấy được bài '{title}' ({lang}): {exc}"

    pages = (data.get("query") or {}).get("pages") or {}
    if not pages:
        return f"Không tìm thấy bài '{title}'."
    page = next(iter(pages.values()))
    extract = page.get("extract", "")
    if not extract:
        return f"Bài '{title}' rỗng hoặc không tồn tại."
    if len(extract) > 8000:
        extract = extract[:8000] + "\n\n[…đã cắt do quá dài]"
    return f"**{page.get('title', title)}**\n\n{extract}"
