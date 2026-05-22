"""vn_news — multi-source news aggregator (VN + international).

Sources (togglable in Studio UI):
- VnExpress, Tuoi Tre, Thanh Nien, Dan Tri (VN)
- BBC News (UK, free RSS)
- Google News (global, free RSS)

Tools:
- list_topics: show available topics
- get_news: fetch news by topic
- search_news: keyword search across feeds
"""

from __future__ import annotations

import logging
from typing import Any

import feedparser
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_news")

# (source_name, rss_url) — each topic has feeds from multiple sources
_VI_SOURCES = [
    ("VnExpress", "vnexpress"),
    ("Tuoi Tre", "tuoitre"),
    ("Thanh Nien", "thanhnien"),
    ("Dan Tri", "dantri"),
]
_INTL_SOURCES = [
    ("BBC News", "bbc_news"),
    ("Google News", "google_news"),
]

_RSS_URLS: dict[str, dict[str, str]] = {
    "vnexpress": {
        "moi_nhat": "https://vnexpress.net/rss/tin-moi-nhat.rss",
        "thoi_su": "https://vnexpress.net/rss/thoi-su.rss",
        "kinh_doanh": "https://vnexpress.net/rss/kinh-doanh.rss",
        "the_thao": "https://vnexpress.net/rss/the-thao.rss",
        "giai_tri": "https://vnexpress.net/rss/giai-tri.rss",
        "phap_luat": "https://vnexpress.net/rss/phap-luat.rss",
        "giao_duc": "https://vnexpress.net/rss/giao-duc.rss",
        "suc_khoe": "https://vnexpress.net/rss/suc-khoe.rss",
        "khoa_hoc": "https://vnexpress.net/rss/khoa-hoc.rss",
        "so_hoa": "https://vnexpress.net/rss/so-hoa.rss",
        "du_lich": "https://vnexpress.net/rss/du-lich.rss",
    },
    "tuoitre": {
        "moi_nhat": "https://tuoitre.vn/rss/tin-moi-nhat.rss",
        "thoi_su": "https://tuoitre.vn/rss/thoi-su.rss",
        "kinh_doanh": "https://tuoitre.vn/rss/kinh-doanh.rss",
    },
    "thanhnien": {
        "moi_nhat": "https://thanhnien.vn/rss/home.rss",
        "the_thao": "https://thanhnien.vn/rss/the-thao.rss",
    },
    "dantri": {
        "moi_nhat": "https://dantri.com.vn/rss/home.rss",
        "thoi_su": "https://dantri.com.vn/rss/xa-hoi.rss",
        "kinh_doanh": "https://dantri.com.vn/rss/kinh-doanh.rss",
        "the_thao": "https://dantri.com.vn/rss/the-thao.rss",
        "giao_duc": "https://dantri.com.vn/rss/giao-duc.rss",
        "suc_khoe": "https://dantri.com.vn/rss/suc-khoe.rss",
    },
    "bbc_news": {
        "moi_nhat": "https://feeds.bbci.co.uk/news/rss.xml",
        "the_gioi": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "kinh_doanh": "https://feeds.bbci.co.uk/news/business/rss.xml",
        "khoa_hoc": "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml",
        "cong_nghe": "https://feeds.bbci.co.uk/news/technology/rss.xml",
    },
    "google_news": {
        "moi_nhat": "https://news.google.com/rss?hl=vi&gl=VN&ceid=VN:vi",
        "the_gioi": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=vi&gl=VN&ceid=VN:vi",
        "kinh_doanh": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=vi&gl=VN&ceid=VN:vi",
        "cong_nghe": "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=vi&gl=VN&ceid=VN:vi",
        "suc_khoe": "https://news.google.com/rss/headlines/section/topic/HEALTH?hl=vi&gl=VN&ceid=VN:vi",
    },
}


def _is_source_enabled(source_key: str) -> bool:
    try:
        from src.sources_config import is_enabled as _chk
        return _chk("vn_news", source_key)
    except Exception:
        return True


def _get_feeds(topic: str) -> list[tuple[str, str]]:
    """Get RSS feed URLs for a topic, filtering by user's Studio toggle config."""
    feeds: list[tuple[str, str]] = []
    # VN sources
    for name, key in _VI_SOURCES:
        if _is_source_enabled(key) and topic in _RSS_URLS.get(key, {}):
            feeds.append((name, _RSS_URLS[key][topic]))
    # International sources
    for name, key in _INTL_SOURCES:
        if _is_source_enabled(key) and topic in _RSS_URLS.get(key, {}):
            feeds.append((name, _RSS_URLS[key][topic]))
    return feeds


# ── Topic list ────────────────────────────────────────────────────────────

TOPICS = {
    "moi_nhat": "Tin moi nhat",
    "thoi_su": "Thoi su",
    "the_gioi": "The gioi",
    "kinh_doanh": "Kinh doanh",
    "the_thao": "The thao",
    "giai_tri": "Giai tri",
    "phap_luat": "Phap luat",
    "giao_duc": "Giao duc",
    "suc_khoe": "Suc khoe",
    "khoa_hoc": "Khoa hoc",
    "cong_nghe": "Cong nghe",
    "so_hoa": "So hoa",
    "du_lich": "Du lich",
}


def _fetch_feed(source: str, url: str) -> list[dict[str, Any]]:
    try:
        feed = feedparser.parse(url)
    except Exception as exc:
        logger.warning("RSS fetch failed for %s: %s", url, exc)
        return []
    items: list[dict[str, Any]] = []
    for entry in feed.entries:
        items.append({
            "source": source,
            "title": entry.get("title", "").strip(),
            "link": entry.get("link", "").strip(),
            "summary": (entry.get("summary") or entry.get("description") or "").strip()[:300],
            "published": entry.get("published", "") or entry.get("updated", ""),
        })
    return items


def _format_items(items: list[dict[str, Any]], limit: int) -> str:
    items = items[:limit]
    if not items:
        return "Không có tin tức nào."
    lines = []
    for i, it in enumerate(items, 1):
        lines.append(
            f"{i}. **{it['title']}** — _{it['source']}_\n"
            f"   {it['summary']}\n"
            f"   {it['link']}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def list_topics() -> str:
    """Liet ke cac chu de tin tuc co san.

    Returns:
        Danh sach topic IDs (vd: moi_nhat, thoi_su, kinh_doanh...).
    """
    lines = []
    for tid, label in TOPICS.items():
        feeds = _get_feeds(tid)
        lines.append(f"- `{tid}` ({label}, {len(feeds)} nguon)")
    return "**Chu de tin tuc:**\n" + "\n".join(lines)


@mcp.tool()
def get_news(topic: str = "moi_nhat", limit: int = 10) -> str:
    """Lay tin tuc moi nhat theo chu de.

    Args:
        topic: Ma chu de (vd: moi_nhat, thoi_su, kinh_doanh, the_gioi...).
               Mac dinh: moi_nhat.
        limit: So bai toi da (1-30, mac dinh 10).

    Returns:
        Danh sach tin tuc: tieu de, tom tat, link, nguon.
    """
    limit = max(1, min(30, limit))
    feeds = _get_feeds(topic.lower())
    if not feeds:
        available = ", ".join(TOPICS.keys())
        return f"Chu de '{topic}' khong co hoac tat ca nguon bi tat. Chu de kha dung: {available}"

    all_items: list[dict[str, Any]] = []
    for source, url in feeds:
        all_items.extend(_fetch_feed(source, url))
    return _format_items(all_items, limit)


@mcp.tool()
def search_news(keyword: str, topic: str = "moi_nhat", limit: int = 10) -> str:
    """Tim tin tuc chua tu khoa.

    Args:
        keyword: Tu khoa can tim trong tieu de/tom tat.
        topic: Chu de gioi han (mac dinh moi_nhat).
        limit: So bai toi da (mac dinh 10).

    Returns:
        Tin tuc khop keyword, sap xep theo moi nhat.
    """
    limit = max(1, min(30, limit))
    feeds = _get_feeds(topic.lower()) or _get_feeds("moi_nhat")
    kw = keyword.lower().strip()
    all_items: list[dict[str, Any]] = []
    for source, url in feeds:
        all_items.extend(_fetch_feed(source, url))
    matched = [
        it for it in all_items
        if kw in it["title"].lower() or kw in it["summary"].lower()
    ]
    if not matched:
        return f"Không tìm thấy tin nào chứa '{keyword}' trong chủ đề '{topic}'."
    return _format_items(matched, limit)
