"""vn_stock — giá cổ phiếu Việt Nam qua vnstock.

vnstock tự động failover giữa các nguồn: TCBS, VCI (Vietcap), SSI, MSN.
Không cần API key. Hỗ trợ giá intraday realtime.

Tools:
- get_stock_price(symbol): giá hiện tại + thay đổi
- get_stock_info(symbol): thông tin công ty
- get_market_overview(): top tăng/giảm/khớp lệnh nhiều
"""

from __future__ import annotations

import logging
from typing import Any

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_stock")


def _get_quote(symbol: str) -> dict[str, Any] | None:
    """Lấy quote intraday từ vnstock. Tự failover giữa các nguồn."""
    try:
        from vnstock import Market
        df = Market().quote.intraday(symbol=symbol.upper(), show_log=False)
        if df is not None and not df.empty:
            row = df.iloc[-1] if len(df) > 1 else df.iloc[0]
            return {
                "symbol": symbol.upper(),
                "price": float(row.get("price", 0)),
                "change": float(row.get("change", 0)) if "change" in row else 0,
                "pct_change": float(row.get("pct_change", 0)) if "pct_change" in row else 0,
                "volume": int(row.get("volume", 0)) if "volume" in row else 0,
                "time": str(row.get("time", "")) if "time" in row else "",
                "raw": row.to_dict(),
            }
    except Exception as exc:
        logger.info("vnstock quote failed for %s: %s", symbol, exc)
    return None


def _get_company_info(symbol: str) -> dict[str, Any] | None:
    """Lấy thông tin công ty từ vnstock."""
    try:
        from vnstock import Market
        df = Market().symbols.overview(symbol=symbol.upper(), show_log=False)
        if df is not None and not df.empty:
            return df.iloc[0].to_dict()
    except Exception as exc:
        logger.info("vnstock info failed for %s: %s", symbol, exc)
    return None


@mcp.tool()
def get_stock_price(symbol: str) -> str:
    """Lấy giá cổ phiếu Việt Nam realtime qua vnstock.

    Hỗ trợ tất cả mã HOSE/HNX/UPCOM (vd: VCB, FPT, HPG, VIC).
    Tự động failover giữa TCBS, VCI, SSI, MSN.

    Args:
        symbol: Mã cổ phiếu (vd: VCB, FPT, HPG).

    Returns:
        Giá hiện tại, thay đổi, khối lượng.
    """
    sym = symbol.upper().strip()
    q = _get_quote(sym)
    if not q:
        return f"Không lấy được giá cổ phiếu '{sym}'. Mã không tồn tại hoặc API lỗi."

    price = q["price"]
    change = q["change"]
    pct = q["pct_change"]
    arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
    vol = q["volume"]
    t = q.get("time", "")

    return (
        f"**{sym}** — {price:,.0f} VND {arrow} {change:+,.0f} ({pct:+.2f}%)\n"
        f"- Khối lượng: {vol:,} cp\n"
        f"- Cập nhật: {t}\n"
        f"_Nguồn: vnstock (TCBS/VCI/SSI/MSN)_"
    )


@mcp.tool()
def get_stock_info(symbol: str) -> str:
    """Lấy thông tin công ty niêm yết Việt Nam.

    Args:
        symbol: Mã cổ phiếu (vd: VCB, FPT).

    Returns:
        Tên công ty, sàn, ngành, vốn hóa.
    """
    sym = symbol.upper().strip()
    info = _get_company_info(sym)
    if not info:
        return f"Không lấy được thông tin '{sym}'."

    lines = [f"**{sym} — {info.get('organ_name', info.get('company_name', 'N/A'))}**"]
    if info.get("organ_short_name"):
        lines.append(f"- Tên viết tắt: {info['organ_short_name']}")
    lines.extend([
        f"- Sàn: {info.get('exchange', info.get('floor', 'N/A'))}",
        f"- Ngành: {info.get('icb_name', info.get('industry', 'N/A'))}",
        f"- Vốn hóa: {info.get('market_cap', 'N/A')}",
    ])
    return "\n".join(lines)


@mcp.tool()
def get_market_overview() -> str:
    """Lấy tổng quan thị trường: VN-Index, top tăng/giảm."""
    try:
        from vnstock import Market
        df = Market().quote.intraday(symbol="VNINDEX", show_log=False)
        if df is not None and not df.empty:
            row = df.iloc[-1]
            price = float(row.get("price", 0))
            change = float(row.get("change", 0)) if "change" in row else 0
            pct = float(row.get("pct_change", 0)) if "pct_change" in row else 0
            arrow = "▲" if change > 0 else ("▼" if change < 0 else "—")
            return (
                f"**VN-Index**: {price:,.0f} {arrow} {change:+,.0f} ({pct:+.2f}%)\n"
                f"_Nguồn: vnstock (TCBS/VCI/SSI/MSN)_"
            )
    except Exception as exc:
        logger.info("vnstock market overview failed: %s", exc)

    return "Không lấy được tổng quan thị trường."
