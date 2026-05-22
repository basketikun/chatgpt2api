"""vn_stock — giá cổ phiếu Việt Nam (HOSE/HNX) qua VNDirect public API.

VNDirect cung cấp endpoint công khai (không cần API key):
- finfo-api.vndirect.com.vn/v4/stocks → metadata
- finfo-api.vndirect.com.vn/v4/stock_prices → giá lịch sử

Tools:
- get_stock_price(symbol): giá hiện tại + thay đổi
- get_stock_info(symbol): thông tin công ty
- get_market_overview(): top tăng/giảm/khớp lệnh nhiều
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

import httpx
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_stock")

VND_PRICE_URL = "https://finfo-api.vndirect.com.vn/v4/stock_prices"
VND_INFO_URL = "https://finfo-api.vndirect.com.vn/v4/stocks"
# Fallback: AlphaVantage free API (rate-limited: 5 calls/min, 500/day)
AV_URL = "https://www.alphavantage.co/query"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}

import urllib.request
import urllib.parse
import json
import os


def _fetch_latest_price(symbol: str) -> dict[str, Any] | None:
    """Try VNDirect first, fallback to AlphaVantage free API."""
    today = date.today()
    week_ago = today - timedelta(days=7)
    params = {
        "sort": "date",
        "size": 5,
        "page": 1,
        "q": f"code:{symbol.upper()}~date:gte:{week_ago.isoformat()}~date:lte:{today.isoformat()}",
    }
    # Try VNDirect
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS, follow_redirects=True) as client:
            r = client.get(VND_PRICE_URL, params=params)
            r.raise_for_status()
        data = r.json()
        items = data.get("data") or []
        if items:
            return items[0]
    except Exception as exc:
        logger.info("VNDirect failed for %s: %s", symbol, exc)

    # Fallback: AlphaVantage free API
    av_key = os.environ.get("ALPHA_VANTAGE_KEY", "demo")
    try:
        av_params = {
            "function": "GLOBAL_QUOTE",
            "symbol": symbol.upper(),
            "apikey": av_key,
        }
        url = AV_URL + "?" + urllib.parse.urlencode(av_params)
        req = urllib.request.Request(url, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        quote = (data.get("Global Quote") or {})
        if quote and quote.get("05. price"):
            price = float(quote.get("05. price", 0))
            change = float(quote.get("09. change", 0))
            change_pct = quote.get("10. change percent", "0%").replace("%", "")
            return {
                "close": price,
                "change": change,
                "pctChange": float(change_pct) if change_pct else 0,
                "open": float(quote.get("02. open", price)),
                "high": float(quote.get("03. high", price)),
                "low": float(quote.get("04. low", price)),
                "nmVolume": int(quote.get("06. volume", 0)),
                "nmValue": 0,
                "floor": quote.get("08. previous close", "N/A"),
                "date": str(today),
            }
    except Exception as exc:
        logger.info("AlphaVantage fallback also failed for %s: %s", symbol, exc)

    return None


def _fetch_info(symbol: str) -> dict[str, Any] | None:
    params = {"q": f"code:{symbol.upper()}"}
    try:
        with httpx.Client(timeout=10.0, headers=HEADERS) as client:
            r = client.get(VND_INFO_URL, params=params)
            r.raise_for_status()
        data = r.json()
    except Exception as exc:
        logger.warning("VND info fetch failed for %s: %s", symbol, exc)
        return None
    items = data.get("data") or []
    return items[0] if items else None


@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """Lấy giá cổ phiếu Việt Nam mới nhất từ VNDirect.

    Args:
        symbol: Mã cổ phiếu HOSE/HNX/UPCOM (vd: VNM, FPT, HPG, VIC).

    Returns:
        Giá đóng cửa, % thay đổi, khối lượng giao dịch.
    """
    sym = symbol.upper().strip()
    p = _fetch_latest_price(sym)
    if not p:
        return f"Không lấy được giá cổ phiếu '{sym}'. Mã không tồn tại hoặc API lỗi."
    change = p.get("change") or 0
    pct = p.get("pctChange") or 0
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
    return (
        f"**{sym}** (sàn {p.get('floor', 'N/A')}) — phiên {p.get('date')}\n"
        f"- Đóng cửa: {p.get('close', 0):,.0f} VND {arrow} {change:+,.0f} ({pct:+.2f}%)\n"
        f"- Mở cửa: {p.get('open', 0):,.0f} | Cao nhất: {p.get('high', 0):,.0f} | Thấp nhất: {p.get('low', 0):,.0f}\n"
        f"- Khối lượng: {p.get('nmVolume', 0):,} cp\n"
        f"- Giá trị: {p.get('nmValue', 0):,.0f} VND"
    )


@mcp.tool()
def get_stock_info(symbol: str) -> str:
    """Lấy thông tin công ty niêm yết Việt Nam.

    Args:
        symbol: Mã cổ phiếu (vd: VNM, FPT).

    Returns:
        Tên công ty, sàn niêm yết, ngành, vốn hóa nếu có.
    """
    sym = symbol.upper().strip()
    info = _fetch_info(sym)
    if not info:
        return f"Không lấy được thông tin '{sym}'."
    lines = [f"**{sym} — {info.get('companyName', 'N/A')}**"]
    if info.get("companyNameEng"):
        lines.append(f"- Tên Anh: {info['companyNameEng']}")
    lines.extend([
        f"- Sàn: {info.get('floor', 'N/A')}",
        f"- Ngành: {info.get('industryName', 'N/A')}",
        f"- Loại: {info.get('type', 'N/A')}",
        f"- Trạng thái: {info.get('status', 'N/A')}",
    ])
    return "\n".join(lines)
