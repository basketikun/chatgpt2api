"""arxiv — search và lấy paper từ ArXiv.

ArXiv có public API miễn phí: export.arxiv.org/api/query (format Atom XML).
Không cần API key. Phù hợp cho user Việt Nam tra cứu nghiên cứu khoa học
(LLM, AI, vật lý, toán học...).

Tools:
- search_papers(query, limit, sort_by): tìm paper theo từ khóa
- get_paper(arxiv_id): chi tiết paper theo ID
"""

from __future__ import annotations

import logging

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("arxiv")

ARXIV_QUERY_URL = "https://export.arxiv.org/api/query"
HEADERS = {"User-Agent": "vn-mcp-hub/0.1 (chatgpt2api)"}


def _fetch(params: dict) -> str:
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS) as client:
            r = client.get(ARXIV_QUERY_URL, params=params)
            r.raise_for_status()
        return r.text
    except Exception as exc:
        logger.warning("ArXiv fetch failed: %s", exc)
        return ""


def _parse_entries(xml: str) -> list[dict]:
    soup = BeautifulSoup(xml, "xml")
    out: list[dict] = []
    for entry in soup.find_all("entry"):
        out.append({
            "title": (entry.title.text if entry.title else "").strip(),
            "summary": (entry.summary.text if entry.summary else "").strip(),
            "id": (entry.id.text if entry.id else "").strip(),
            "published": (entry.published.text if entry.published else "").strip(),
            "authors": [a.find("name").text for a in entry.find_all("author") if a.find("name")],
            "categories": [c.get("term", "") for c in entry.find_all("category")],
        })
    return out


def _format_entries(entries: list[dict], limit: int) -> str:
    items = entries[:limit]
    if not items:
        return "Không tìm thấy paper nào khớp."
    lines = []
    for i, p in enumerate(items, 1):
        authors = ", ".join(p["authors"][:5])
        if len(p["authors"]) > 5:
            authors += ", ..."
        cats = ", ".join(p["categories"][:3])
        summary = (p["summary"][:300] + "...") if len(p["summary"]) > 300 else p["summary"]
        lines.append(
            f"{i}. **{p['title']}**\n"
            f"   _Tác giả:_ {authors}\n"
            f"   _Phân loại:_ {cats}  |  _Ngày:_ {p['published'][:10]}\n"
            f"   {summary}\n"
            f"   {p['id']}"
        )
    return "\n\n".join(lines)


@mcp.tool()
def search_papers(query: str, limit: int = 10, sort_by: str = "relevance") -> str:
    """Tìm paper khoa học trên ArXiv.

    Args:
        query: Từ khóa (vd: "large language model", "quantum computing",
               "transformer attention").
        limit: Số kết quả tối đa (1-50, mặc định 10).
        sort_by: 'relevance' | 'submittedDate' | 'lastUpdatedDate'. Mặc định 'relevance'.

    Returns:
        Danh sách paper khớp gồm tiêu đề, tác giả, tóm tắt, link.
    """
    limit = max(1, min(50, limit))
    sort_by = sort_by if sort_by in {"relevance", "submittedDate", "lastUpdatedDate"} else "relevance"
    xml = _fetch({
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": limit,
        "sortBy": sort_by,
        "sortOrder": "descending",
    })
    if not xml:
        return f"Lỗi truy vấn ArXiv cho '{query}'."
    entries = _parse_entries(xml)
    return _format_entries(entries, limit)


@mcp.tool()
def get_paper(arxiv_id: str) -> str:
    """Lấy chi tiết một paper ArXiv theo ID.

    Args:
        arxiv_id: ID paper (vd: "2401.12345" hoặc URL "https://arxiv.org/abs/...").

    Returns:
        Chi tiết paper: tiêu đề, tác giả, abstract, link.
    """
    aid = arxiv_id.strip()
    if "arxiv.org" in aid:
        aid = aid.rstrip("/").split("/")[-1]
    xml = _fetch({"id_list": aid})
    if not xml:
        return f"Lỗi tải paper '{arxiv_id}'."
    entries = _parse_entries(xml)
    if not entries:
        return f"Không tìm thấy paper ID '{arxiv_id}'."
    p = entries[0]
    return (
        f"**{p['title']}**\n\n"
        f"_Tác giả:_ {', '.join(p['authors'])}\n"
        f"_Phân loại:_ {', '.join(p['categories'])}\n"
        f"_Ngày:_ {p['published'][:10]}\n\n"
        f"**Abstract:**\n{p['summary']}\n\n"
        f"_Link:_ {p['id']}"
    )
