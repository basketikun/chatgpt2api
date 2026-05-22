"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam qua csgt.bocongan.gov.vn.

Trang chính thức của Cục CSGT (Bộ Công An):
  https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi

Domain cũ csgt.vn đã redirect 302 sang bocongan.gov.vn (không còn dùng).

Form yêu cầu:
- Loại phương tiện: Xe ô tô / Xe máy / Xe đạp điện
- Biển số xe
- Google reCAPTCHA — điểm tắc nghẽn cho tra cứu tự động

Do reCAPTCHA, tool này best-effort: cung cấp link form + hướng dẫn chi tiết.
"""

from __future__ import annotations

import logging
import re

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_phat_nguoi")

CSGT_PAGE = "https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi"

VEHICLE_TYPES = {
    "oto": ("Ô tô"),
    "ô tô": ("Ô tô"),
    "car": ("Ô tô"),
    "xemay": ("Xe máy"),
    "xe máy": ("Xe máy"),
    "motorbike": ("Xe máy"),
    "xedien": ("Xe đạp điện"),
    "xe đạp điện": ("Xe đạp điện"),
    "electricbike": ("Xe đạp điện"),
}

# Biển số VN: 2 số + 1-2 chữ + - + 4-5 số
# Ví dụ hợp lệ: 30A-12345, 29K3-1234, 51-F3-1234.56
PLATE_PATTERN = re.compile(
    r"^\d{2}[A-Z]{1,2}-?\d{4,5}(\.\d{2})?$", re.IGNORECASE
)


def _normalise_plate(plate: str) -> str:
    p = plate.strip().upper().replace(" ", "")
    if "-" not in p and len(p) >= 7:
        p = f"{p[:3]}-{p[3:]}"
    return p


def _is_valid_plate(plate: str) -> bool:
    return bool(PLATE_PATTERN.match(plate))


@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam.

    Trang chính thức của Cục CSGT (Bộ Công An) yêu cầu xác thực reCAPTCHA
    nên không thể tra cứu hoàn toàn tự động. Tool cung cấp link + hướng dẫn.

    Args:
        plate: Biển số xe (vd: "30A-12345", "34A47645").
        vehicle_type: 'oto' / 'xe máy' / 'xe đạp điện'. Mặc định oto.

    Returns:
        Hướng dẫn tra cứu kèm URL trực tiếp đến form chính phủ.
    """
    norm_plate = _normalise_plate(plate)
    if not _is_valid_plate(norm_plate):
        return (
            f"Biển số '{plate}' không đúng định dạng VN.\n"
            "Định dạng đúng: XX(A-Z)-12345 hoặc 29-K3-1234.56"
        )

    vt_key = vehicle_type.lower().strip()
    vt_label = VEHICLE_TYPES.get(vt_key)
    if not vt_label:
        return (
            f"Loại xe '{vehicle_type}' không hợp lệ. "
            f"Chọn: ô tô, xe máy, xe đạp điện."
        )

    return (
        f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
        f"1. Mở trang: {CSGT_PAGE}\n"
        f"2. Chọn loại phương tiện: **{vt_label}**\n"
        f"3. Nhập biển số: `{norm_plate}`\n"
        f"4. Xác thực reCAPTCHA (bắt buộc)\n"
        f"5. Bấm **Tra cứu**\n\n"
        f"⚠️ Trang yêu cầu reCAPTCHA nên không thể tra cứu tự động.\n"
        f"📌 Nguồn: Cục Cảnh sát Giao thông — csgt.bocongan.gov.vn"
    )


@mcp.tool()
def list_vehicle_types() -> str:
    """Liệt kê các loại xe được hỗ trợ tra cứu phạt nguội."""
    seen = set()
    out = ["**Loại xe hỗ trợ tra cứu phạt nguội:**", ""]
    for key, label in VEHICLE_TYPES.items():
        if label in seen:
            continue
        seen.add(label)
        out.append(f"- {label}")
    out.append("")
    out.append(f"📌 Truy cập: {CSGT_PAGE}")
    return "\n".join(out)
