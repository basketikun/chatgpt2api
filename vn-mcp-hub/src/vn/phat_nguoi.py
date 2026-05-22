"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam qua csgt.bocongan.gov.vn.

Trang chính thức của Cục CSGT: https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi
Form yêu cầu:
- Loại xe: car / motorbike / electricbike
- Biển số xe (vd: 34A47645)
- Google reCAPTCHA v2 — đây là điểm tắc nghẽn

Tools best-effort: trả URL form + hướng dẫn. Có hỗ trợ tra cứu tự động khi
có reCAPTCHA bypass token.
"""

from __future__ import annotations

import logging
import re
import json
import urllib.request
from datetime import datetime, timezone

from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_phat_nguoi")

CSGT_PAGE = "https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi"
CSGT_API = "https://csgt.bocongan.gov.vn/api/tra-cuu-phat-nguoi"

VEHICLE_TYPES = {
    "oto": ("car", "Ô tô"),
    "ô tô": ("car", "Ô tô"),
    "car": ("car", "Ô tô"),
    "xemay": ("motorbike", "Xe máy"),
    "xe máy": ("motorbike", "Xe máy"),
    "motorbike": ("motorbike", "Xe máy"),
    "xedien": ("electricbike", "Xe đạp điện"),
    "xe đạp điện": ("electricbike", "Xe đạp điện"),
    "electricbike": ("electricbike", "Xe đạp điện"),
}

# Biển số VN: 2 số + 1-2 chữ + - + 4-5 số (vd: 30A-12345, 29-K3-1234.56)
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


def _fetch_csrf_token() -> str | None:
    """Lấy CSRF token từ trang tra cứu phạt nguội."""
    try:
        req = urllib.request.Request(CSGT_PAGE, headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html",
        })
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")
        # Laravel CSRF token: <input type="hidden" name="_token" value="...">
        m = re.search(r'name="_token"\s+value="([^"]+)"', html)
        if m:
            return m.group(1)
        # Alternative pattern
        m = re.search(r'<input[^>]+name="_token"[^>]+value="([^"]+)"', html)
        if m:
            return m.group(1)
    except Exception as exc:
        logger.warning("CSGT CSRF fetch failed: %s", exc)
    return None


def _try_api_query(plate: str, vehicle_type: str, csrf_token: str | None = None) -> dict | None:
    """Best-effort: thử gọi API tra cứu phạt nguội. Trả về None nếu thất bại.

    Cần reCAPTCHA token để thành công, nếu không API sẽ từ chối.
    """
    if not csrf_token:
        csrf_token = _fetch_csrf_token()
    if not csrf_token:
        return None

    payload = {
        "plate_number": plate,
        "vehicle_type": vehicle_type,
        "_token": csrf_token,
    }

    try:
        req = urllib.request.Request(CSGT_API, data=json.dumps(payload).encode(),
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/json",
                "X-CSRF-TOKEN": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        return data
    except Exception as exc:
        logger.info("CSGT API query failed (expected without captcha): %s", exc)

    # Fallback: thử form POST
    try:
        form_data = urllib.parse.urlencode({
            "plate_number": plate,
            "vehicle_type": vehicle_type,
            "_token": csrf_token,
        }).encode()
        req = urllib.request.Request(CSGT_PAGE, data=form_data,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRF-TOKEN": csrf_token,
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json",
            })
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read().decode())
        return data
    except Exception as exc:
        logger.info("CSGT form POST also failed: %s", exc)

    return None


@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam qua csgt.bocongan.gov.vn.

    Trang chính thức của Cục CSGT yêu cầu reCAPTCHA nên không thể tra cứu
    hoàn toàn tự động. Tool cung cấp hướng dẫn + link form.

    Args:
        plate: Biển số xe (vd: "30A-12345", "34A47645").
        vehicle_type: Loại xe ('oto', 'xe máy', 'xe đạp điện'). Mặc định oto.

    Returns:
        Hướng dẫn tra cứu kèm URL form, biển số đã chuẩn hóa.
    """
    norm_plate = _normalise_plate(plate)
    if not _is_valid_plate(norm_plate):
        return (
            f"Biển số '{plate}' không đúng định dạng VN.\n"
            "Định dạng đúng: XX(A-Z)-12345 hoặc 29-K3-1234.56"
        )

    vt_key = vehicle_type.lower().strip()
    vt = VEHICLE_TYPES.get(vt_key)
    if not vt:
        return (
            f"Loại xe '{vehicle_type}' không hợp lệ. "
            f"Chọn: ô tô, xe máy, xe đạp điện."
        )
    code, vt_label = vt

    lines = [
        f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**",
        "",
        f"1. Mở trang: {CSGT_PAGE}",
        f"2. Chọn loại phương tiện: **{vt_label}**",
        f"3. Nhập biển số: `{norm_plate}`",
        f"4. Xác thực reCAPTCHA",
        f"5. Bấm **Tra cứu**",
        "",
        f"_Nguồn: Cục Cảnh sát Giao thông — csgt.bocongan.gov.vn_",
    ]

    # Best-effort: thử gọi API
    token = _fetch_csrf_token()
    if token:
        result = _try_api_query(norm_plate, code, token)
        if result:
            if result.get("status"):
                violations = result.get("data", result.get("violations", []))
                if violations:
                    lines.append("")
                    lines.append("**Kết quả tra cứu:**")
                    if isinstance(violations, list):
                        for v in violations[:5]:
                            if isinstance(v, dict):
                                lines.append(
                                    f"- {v.get('violation', v.get('hanh_vi', 'N/A'))}: "
                                    f"{v.get('fine', v.get('tien_phat', 'N/A'))}"
                                )
                            else:
                                lines.append(f"- {v}")
                    lines.append("")
    else:
        logger.info("CSGT: could not fetch CSRF token, returning instructions only")

    return "\n".join(lines)


@mcp.tool()
def list_vehicle_types() -> str:
    """Liệt kê các loại xe được hỗ trợ tra cứu phạt nguội.

    Returns:
        Danh sách loại xe.
    """
    seen = set()
    out = ["**Loại xe hỗ trợ tra cứu phạt nguội:**", ""]
    for key, (code, label) in VEHICLE_TYPES.items():
        if code in seen:
            continue
        seen.add(code)
        out.append(f"- {label} (mã `{code}`)")
    out.append("")
    out.append(f"Truy cập: {CSGT_PAGE}")
    return "\n".join(out)


@mcp.tool()
def get_csgt_page_info() -> str:
    """Lấy thông tin về trang tra cứu phạt nguội chính thức.

    Returns:
        URL, CSRF token hiện tại, thời gian cập nhật.
    """
    token = _fetch_csrf_token()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"**Trang tra cứu phạt nguội chính thức:**\n"
        f"- URL: {CSGT_PAGE}\n"
        f"- Domain: csgt.bocongan.gov.vn (Bộ Công An)\n"
        f"- CSRF token: {'Có (' + token[:8] + '...)' if token else 'Không lấy được'}\n"
        f"- reCAPTCHA: Google reCAPTCHA v2\n"
        f"- Thời gian: {now} UTC\n"
    )
