"""vn_lunar — lịch âm Việt Nam, ngày tốt xấu, can chi.

Uses lunarcalendar (pip) for solar↔lunar conversion. The library produces
Chinese lunar dates which match Vietnamese lunar except for a small offset
on a few days; for everyday user queries this is accurate enough.

Tools:
- get_today_lunar: hôm nay ngày âm bao nhiêu
- solar_to_lunar(year, month, day): convert dương → âm
- lunar_to_solar(year, month, day, leap): convert âm → dương
- get_can_chi(year): tính can chi của năm âm
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from fastmcp import FastMCP

mcp = FastMCP("vn_lunar")

CAN = ["Giáp", "Ất", "Bính", "Đinh", "Mậu", "Kỷ", "Canh", "Tân", "Nhâm", "Quý"]
CHI = ["Tý", "Sửu", "Dần", "Mão", "Thìn", "Tỵ", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"]

LUNAR_MONTH_NAMES = {
    1: "Giêng", 2: "Hai", 3: "Ba", 4: "Tư", 5: "Năm", 6: "Sáu",
    7: "Bảy", 8: "Tám", 9: "Chín", 10: "Mười", 11: "Một", 12: "Chạp",
}


def _can_chi_year(year: int) -> str:
    """Tính tên năm âm theo can chi (vd 2026 → 'Bính Ngọ')."""
    can = CAN[(year - 4) % 10]
    chi = CHI[(year - 4) % 12]
    return f"{can} {chi}"


def _convert_solar_to_lunar(y: int, m: int, d: int) -> dict[str, Any]:
    from lunarcalendar import Solar, Converter
    solar = Solar(y, m, d)
    lunar = Converter.Solar2Lunar(solar)
    return {
        "year": lunar.year,
        "month": lunar.month,
        "day": lunar.day,
        "is_leap": bool(lunar.isleap),
        "year_can_chi": _can_chi_year(lunar.year),
        "month_name": LUNAR_MONTH_NAMES.get(lunar.month, str(lunar.month)),
    }


def _convert_lunar_to_solar(y: int, m: int, d: int, is_leap: bool = False) -> dict[str, Any]:
    from lunarcalendar import Lunar, Converter
    lunar = Lunar(y, m, d, isleap=is_leap)
    solar = Converter.Lunar2Solar(lunar)
    return {"year": solar.year, "month": solar.month, "day": solar.day}


@mcp.tool()
def get_today_lunar() -> str:
    """Lấy ngày âm hôm nay tại Việt Nam.

    Returns:
        Ngày âm chi tiết: tháng (tên tiếng Việt), ngày, năm âm với can chi.
    """
    today = date.today()
    info = _convert_solar_to_lunar(today.year, today.month, today.day)
    leap_note = " (nhuận)" if info["is_leap"] else ""
    return (
        f"**Hôm nay ({today.isoformat()}):**\n"
        f"- Ngày {info['day']} tháng {info['month_name']}{leap_note} năm {info['year']} âm lịch\n"
        f"- Năm: {info['year_can_chi']}"
    )


@mcp.tool()
def solar_to_lunar(year: int, month: int, day: int) -> str:
    """Chuyển ngày dương lịch sang âm lịch.

    Args:
        year: Năm dương (vd: 2026).
        month: Tháng dương (1-12).
        day: Ngày dương (1-31).

    Returns:
        Ngày âm tương ứng kèm tên năm theo can chi.
    """
    try:
        info = _convert_solar_to_lunar(year, month, day)
    except Exception as exc:
        return f"Không chuyển được {year}-{month:02d}-{day:02d}: {exc}"
    leap_note = " (nhuận)" if info["is_leap"] else ""
    return (
        f"**Dương lịch {year}-{month:02d}-{day:02d}:**\n"
        f"- Âm lịch: ngày {info['day']} tháng {info['month_name']}{leap_note} năm {info['year']}\n"
        f"- Năm âm: {info['year_can_chi']}"
    )


@mcp.tool()
def lunar_to_solar(year: int, month: int, day: int, is_leap: bool = False) -> str:
    """Chuyển ngày âm lịch sang dương lịch.

    Args:
        year: Năm âm.
        month: Tháng âm (1-12).
        day: Ngày âm (1-30).
        is_leap: True nếu là tháng nhuận. Mặc định False.

    Returns:
        Ngày dương lịch tương ứng (ISO format).
    """
    try:
        out = _convert_lunar_to_solar(year, month, day, is_leap)
    except Exception as exc:
        return f"Không chuyển được âm {year}-{month:02d}-{day:02d}: {exc}"
    leap_note = " (nhuận)" if is_leap else ""
    return (
        f"**Âm lịch ngày {day} tháng {month}{leap_note} năm {year}:**\n"
        f"- Dương lịch: {out['year']:04d}-{out['month']:02d}-{out['day']:02d}"
    )


@mcp.tool()
def get_can_chi(year: int) -> str:
    """Tính tên năm âm theo can chi (Giáp Tý, Ất Sửu, ...).

    Args:
        year: Năm âm hoặc dương (cùng năm âm lịch).

    Returns:
        Tên năm theo can chi tiếng Việt.
    """
    return f"Năm {year}: **{_can_chi_year(year)}**"
