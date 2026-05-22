"""vn_law — tra cứu văn bản pháp luật Việt Nam.

Sources:
- thuvienphapluat.vn: search engine + document detail (HTML scrape)
- vbpl.vn: cổng thông tin văn bản pháp luật chính phủ (HTML scrape)

Tools:
- search_law(keyword, limit): tìm văn bản theo từ khóa
- get_law_detail(url): lấy nội dung đầy đủ 1 văn bản

Best-effort scraper: site có thể đổi structure, có thể bị anti-bot. Khi fail
trả về thông báo thay vì exception.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_law")

TVPL_SEARCH = "https://thuvienphapluat.vn/page/tim-van-ban.aspx"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
}


def _search_tvpl(keyword: str) -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True, headers=HEADERS) as client:
            r = client.get(TVPL_SEARCH, params={"keyword": keyword, "type": "0"})
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.warning("TVPL search failed for '%s': %s", keyword, exc)
        return []
    results: list[dict[str, Any]] = []
    for item in soup.select("p.nqTitle a, .item-title a, h3 a"):
        title = item.get_text(strip=True)
        link = item.get("href") or ""
        if not title or not link:
            continue
        if not link.startswith("http"):
            link = f"https://thuvienphapluat.vn{link}"
        results.append({"title": title, "link": link})
        if len(results) >= 30:
            break
    return results


def _fetch_doc(url: str) -> str:
    try:
        with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
            r = client.get(url)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        return f"Lỗi tải văn bản: {exc}"
    body = (
        soup.select_one(".cldivContentDocVn")
        or soup.select_one(".content-document")
        or soup.select_one("#tab1")
        or soup.body
    )
    if not body:
        return "Không trích xuất được nội dung văn bản."
    text = body.get_text("\n", strip=True)
    if len(text) > 8000:
        text = text[:8000] + "\n\n[…đã cắt do quá dài]"
    return text


@mcp.tool()
def search_law(keyword: str, limit: int = 10) -> str:
    """Tìm văn bản pháp luật Việt Nam theo từ khóa qua thuvienphapluat.vn.

    Args:
        keyword: Từ khóa (vd: "Luật doanh nghiệp 2020", "Nghị định 100/2019").
        limit: Số kết quả tối đa (1-30, mặc định 10).

    Returns:
        Danh sách văn bản khớp gồm tiêu đề + link tới chi tiết.
    """
    limit = max(1, min(30, limit))
    results = _search_tvpl(keyword)
    if not results:
        return f"Không tìm thấy văn bản nào khớp '{keyword}' (hoặc site đang chặn truy cập)."
    items = results[:limit]
    lines = [f"**{len(items)} văn bản khớp '{keyword}':**", ""]
    for i, r in enumerate(items, 1):
        lines.append(f"{i}. **{r['title']}**\n   {r['link']}")
    return "\n".join(lines)


@mcp.tool()
def get_law_detail(url: str) -> str:
    """Lấy nội dung đầy đủ một văn bản pháp luật từ URL.

    Args:
        url: URL trang chi tiết (vd: từ search_law).

    Returns:
        Toàn văn pháp luật (cắt 8000 ký tự nếu quá dài).
    """
    if not url.startswith("http"):
        return "URL không hợp lệ — phải bắt đầu bằng http(s)."
    return _fetch_doc(url)
