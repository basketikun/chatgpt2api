"""vn_petrol — giá xăng dầu bán lẻ Petrolimex.

Source: webgia.com (stable HTML scrape of the Petrolimex retail board).
Petrolimex publishes the same prices but their portal renders client-side
and 403s on direct API calls — webgia mirrors the same table in static
HTML which is easy to parse.

Tools:
- get_petrol_prices(region="all"): bảng giá hiện tại theo Vùng 1 / Vùng 2
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_petrol")

PETROL_URL = "https://webgia.com/gia-xang-dau/petrolimex/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")


def _fetch_petrol() -> dict[str, Any]:
    """Scrape the Petrolimex retail price table from webgia.com.

    Returns dict with `updated_at` and `rows` = list of
    {product, vung_1, vung_2} entries.
    """
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.get(PETROL_URL, headers={"User-Agent": UA})
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.warning("Petrol fetch failed: %s", exc)
        return {"updated_at": "", "rows": []}

    # The first .table with thead "Sản phẩm | Vùng 1 | Vùng 2" is the retail
    # table. Other tables on the page are historical-change rows we don't want.
    rows: list[dict[str, str]] = []
    for table in soup.find_all("table"):
        thead = table.find("thead")
        if not thead or "Sản phẩm" not in thead.get_text():
            continue
        body = table.find("tbody")
        if not body:
            continue
        for tr in body.find_all("tr"):
            cells = tr.find_all(["th", "td"])
            if len(cells) < 3:
                continue
            product = cells[0].get_text(strip=True)
            v1 = cells[1].get_text(strip=True)
            v2 = cells[2].get_text(strip=True)
            if product and v1:
                rows.append({"product": product, "vung_1": v1, "vung_2": v2})
        if rows:
            break  # first matching table is the current retail board

    # Updated-at is in the <h1><small> tag.
    updated_at = ""
    h1 = soup.find("h1")
    if h1:
        small = h1.find("small")
        if small:
            updated_at = small.get_text(strip=True).lstrip("- ").strip()

    return {"updated_at": updated_at, "rows": rows}


@mcp.tool()
def get_petrol_prices(region: str = "all") -> str:
    """Lấy giá bán lẻ xăng dầu Petrolimex hôm nay (Vùng 1 và Vùng 2).

    Args:
        region: "vung1" / "vung2" / "all" (mặc định). Vùng 1 áp dụng cho
            các đô thị lớn (Hà Nội, TP.HCM, Đà Nẵng, Cần Thơ...); Vùng 2
            cao hơn ~500-600đ/lít cho các tỉnh vùng sâu vùng xa.

    Returns:
        Bảng giá Markdown gồm Xăng RON 95-V/III, E5 RON 92-II, E10 RON 95-III,
        Dầu DO 0,001S-V / DO 0,05S-II, Dầu hỏa 2-K, Mazút N. Đơn vị đồng/lít
        (hoặc đồng/kg với Mazút). Nguồn webgia.com / Petrolimex.
    """
    region = region.lower().strip()
    data = _fetch_petrol()
    rows = data.get("rows") or []
    if not rows:
        return "Không lấy được bảng giá xăng dầu Petrolimex lúc này."

    lines = [f"**Giá bán lẻ xăng dầu Petrolimex — cập nhật {data.get('updated_at') or 'mới nhất'}:**", ""]
    if region in ("vung1", "vung_1", "1"):
        lines.append("| Sản phẩm | Vùng 1 (đồng) |")
        lines.append("|---|---:|")
        for r in rows:
            lines.append(f"| {r['product']} | {r['vung_1']} |")
    elif region in ("vung2", "vung_2", "2"):
        lines.append("| Sản phẩm | Vùng 2 (đồng) |")
        lines.append("|---|---:|")
        for r in rows:
            lines.append(f"| {r['product']} | {r['vung_2']} |")
    else:
        lines.append("| Sản phẩm | Vùng 1 | Vùng 2 |")
        lines.append("|---|---:|---:|")
        for r in rows:
            lines.append(f"| {r['product']} | {r['vung_1']} | {r['vung_2']} |")

    lines.append("")
    lines.append("_Vùng 1 = đô thị lớn; Vùng 2 = vùng sâu vùng xa (cao hơn ~500-600đ/lít)._")
    lines.append("_Nguồn: webgia.com (mirror Petrolimex retail board)._")
    return "\n".join(lines)
