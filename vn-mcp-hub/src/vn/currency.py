"""vn_currency — tỷ giá ngoại tệ và giá vàng Việt Nam.

Sources:
- Vietcombank: portal.vietcombank.com.vn (XML rate feed)
- SJC: sjc.com.vn (HTML scrape gold prices)
- ExchangeRate-API: open.er-api.com (cross-currency fallback)

Tools:
- get_exchange_rate(base, quote): tỷ giá 2 đồng tiền
- get_vcb_rates(): toàn bộ tỷ giá Vietcombank
- get_gold_prices(): giá vàng SJC theo loại
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_currency")

VCB_RATES_URL = "https://portal.vietcombank.com.vn/Usercontrols/TVPortal.TyGia/pXML.aspx"
SJC_URL = "https://sjc.com.vn/giavang/textContent.php"
DOJI_URL = "https://giavang.doji.vn/"
EXR_URL = "https://open.er-api.com/v6/latest/{base}"


def _fetch_vcb() -> list[dict[str, Any]]:
    """Vietcombank XML feed — list of {currency, name, buy, sell, transfer}."""
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.get(VCB_RATES_URL)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "xml")
    except Exception as exc:
        logger.warning("VCB fetch failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for ex in soup.find_all("Exrate"):
        out.append({
            "currency": (ex.get("CurrencyCode") or "").strip(),
            "name": (ex.get("CurrencyName") or "").strip(),
            "buy": (ex.get("Buy") or "").strip(),
            "transfer": (ex.get("Transfer") or "").strip(),
            "sell": (ex.get("Sell") or "").strip(),
        })
    return out


def _fetch_sjc() -> list[dict[str, Any]]:
    """SJC HTML scrape — gold prices by type."""
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True) as client:
            r = client.get(SJC_URL)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.warning("SJC fetch failed: %s", exc)
        return []
    rows: list[dict[str, Any]] = []
    for tr in soup.find_all("tr"):
        cols = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cols) < 3:
            continue
        rows.append({"type": cols[0], "buy": cols[1], "sell": cols[2]})
    return rows


def _fetch_doji() -> list[dict[str, Any]]:
    """DOJI HTML scrape — gold prices by type."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    try:
        with httpx.Client(timeout=10.0, follow_redirects=True, headers=headers) as client:
            r = client.get(DOJI_URL)
            r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
    except Exception as exc:
        logger.warning("DOJI fetch failed: %s", exc)
        return []
    
    tables = soup.find_all("table")
    if not tables:
        return []
    
    rows: list[dict[str, Any]] = []
    # Extract from the first table which contains the retail gold rates
    table = tables[0]
    for tr in table.find_all("tr"):
        cols = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if len(cols) < 3 or cols[0] in ("Giá vàng trong nước", "Loại"):
            continue
        rows.append({"type": cols[0], "buy": cols[1], "sell": cols[2]})
    return rows


def _fetch_er(base: str = "USD") -> dict[str, float]:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(EXR_URL.format(base=base.upper()))
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("ExchangeRate API failed: %s", exc)
        return {}
    if data.get("result") != "success":
        return {}
    return {k: float(v) for k, v in (data.get("rates") or {}).items()}


@mcp.tool()
def get_vcb_rates() -> str:
    """Lấy toàn bộ tỷ giá hối đoái Vietcombank (VND) cho các ngoại tệ.

    Returns:
        Bảng tỷ giá USD, EUR, JPY, CNY, GBP, AUD, KRW, etc. với giá mua tiền mặt,
        chuyển khoản, và bán.
    """
    rates = _fetch_vcb()
    if not rates:
        return "Không lấy được tỷ giá Vietcombank lúc này."
    lines = ["**Tỷ giá Vietcombank (VND):**", "", "| Mã | Tên | Mua TM | Mua CK | Bán |", "|---|---|---:|---:|---:|"]
    for r in rates:
        lines.append(f"| {r['currency']} | {r['name']} | {r['buy']} | {r['transfer']} | {r['sell']} |")
    return "\n".join(lines)


@mcp.tool()
def get_exchange_rate(base: str = "USD", quote: str = "VND") -> str:
    """Lấy tỷ giá giữa 2 loại tiền tệ.

    Args:
        base: Mã tiền nguồn (vd: USD, EUR). Mặc định USD.
        quote: Mã tiền đích (vd: VND, JPY). Mặc định VND.

    Returns:
        Tỷ giá hiện tại từ ExchangeRate-API. Cho cặp X-VND, ưu tiên Vietcombank.
    """
    base = base.upper().strip()
    quote = quote.upper().strip()
    if quote == "VND":
        rates = _fetch_vcb()
        for r in rates:
            if r["currency"] == base:
                return (
                    f"**1 {base} = ? VND (Vietcombank)**\n"
                    f"- Mua tiền mặt: {r['buy']}\n"
                    f"- Mua chuyển khoản: {r['transfer']}\n"
                    f"- Bán: {r['sell']}"
                )
    rates_map = _fetch_er(base)
    if quote in rates_map:
        return f"1 {base} = {rates_map[quote]:,.4f} {quote} (ExchangeRate-API)"
    return f"Không lấy được tỷ giá {base}/{quote}."


@mcp.tool()
def get_gold_prices(brand: str = "all") -> str:
    """Lấy giá vàng hôm nay tại Việt Nam từ SJC và DOJI.

    Args:
        brand: Thương hiệu vàng cần lấy ("sjc", "doji", hoặc "all" để lấy cả hai). Mặc định "all".

    Returns:
        Bảng giá vàng chi tiết kèm giá mua vào/bán ra.
    """
    brand = brand.lower().strip()
    lines = []
    
    if brand in ("sjc", "all"):
        sjc_rows = _fetch_sjc()
        if sjc_rows:
            lines.append("**Giá vàng SJC hôm nay:**")
            lines.append("")
            lines.append("| Loại vàng | Mua vào | Bán ra |")
            lines.append("|---|---:|---:|")
            for r in sjc_rows:
                lines.append(f"| {r['type']} | {r['buy']} | {r['sell']} |")
            lines.append("\n_Đơn vị SJC: nghìn đồng/lượng. Nguồn: sjc.com.vn_")
        elif brand == "sjc":
            return "Không lấy được giá vàng SJC lúc này."
            
    if brand in ("doji", "all"):
        if lines:
            lines.append("\n" + "─" * 40 + "\n")
        doji_rows = _fetch_doji()
        if doji_rows:
            lines.append("**Giá vàng DOJI hôm nay:**")
            lines.append("")
            lines.append("| Loại vàng | Mua vào | Bán ra |")
            lines.append("|---|---:|---:|")
            for r in doji_rows:
                lines.append(f"| {r['type']} | {r['buy']} | {r['sell']} |")
            lines.append("\n_Đơn vị DOJI: nghìn đồng/chỉ (1 lượng = 10 chỉ). Nguồn: giavang.doji.vn_")
        elif brand == "doji":
            return "Không lấy được giá vàng DOJI lúc này."
            
    if not lines:
        return "Không lấy được thông tin giá vàng lúc này."
        
    return "\n".join(lines)
