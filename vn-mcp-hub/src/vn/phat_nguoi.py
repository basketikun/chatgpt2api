"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam.

API chính thức của CSGT (csgt.vn):
1. GET captcha ảnh → OCR bằng Tesseract
2. POST form tra cứu
3. Parse kết quả từ HTML
"""

from __future__ import annotations

import logging
import re
import io
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_phat_nguoi")

# ── Constants ──
BASE_URL = "https://www.csgt.vn"
CAPTCHA_URL = f"{BASE_URL}/lib/captcha/captcha.class.php"
POST_URL = f"{BASE_URL}/?mod=contact&task=tracuu_post&ajax"
RESULTS_URL = f"{BASE_URL}/tra-cuu-phuong-tien-vi-pham.html"

VEHICLE_TYPES = {
    "oto": ("1", "Ô tô"), "ô tô": ("1", "Ô tô"), "car": ("1", "Ô tô"),
    "xemay": ("2", "Xe máy"), "xe máy": ("2", "Xe máy"),
    "motorbike": ("2", "Xe máy"),
    "xedien": ("3", "Xe đạp điện"),
    "xe đạp điện": ("3", "Xe đạp điện"),
    "electricbike": ("3", "Xe đạp điện"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

PLATE_PATTERN = re.compile(r"^\d{2}[A-Z0-9]{1,2}-?\d{4,5}(\.\d{2})?$", re.I)


def _normalise_plate(plate: str) -> str:
    p = plate.strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^(\d{2}[A-Z0-9]{1,2})(\d{4,5})$", p)
    return f"{m.group(1)}-{m.group(2)}" if m else plate


@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam qua CSGT.

    Args:
        plate: Biển số xe (vd: "34A47645", "99A40201").
        vehicle_type: 'oto' / 'xe máy' / 'xe đạp điện'. Mặc định oto.

    Returns:
        Kết quả tra cứu: danh sách vi phạm hoặc thông báo không có.
    """
    norm_plate = _normalise_plate(plate)
    vt_key = vehicle_type.lower().strip()
    vt = VEHICLE_TYPES.get(vt_key)
    if not vt:
        return f"Loại xe '{vehicle_type}' không hợp lệ. Chọn: ô tô, xe máy, xe đạp điện."
    code, vt_label = vt

    # 1) Get CAPTCHA image + OCR
    captcha_text = ""
    try:
        req = urllib.request.Request(CAPTCHA_URL, headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=10)
        img_data = resp.read()
        if img_data and len(img_data) > 100:
            try:
                import pytesseract
                from PIL import Image
                img = Image.open(io.BytesIO(img_data))
                captcha_text = pytesseract.image_to_string(
                    img, config="--psm 7 -c tessedit_char_whitelist=0123456789"
                ).strip()
            except ImportError:
                pass
    except Exception as exc:
        logger.warning("CAPTCHA fetch failed: %s", exc)

    if not captcha_text:
        captcha_text = "0000"  # Fallback

    # 2) POST form
    form_data = urllib.parse.urlencode({
        "BienKS": norm_plate.replace("-", ""),
        "Xe": code,
        "captcha": captcha_text,
        "ipClient": "9.9.9.91",
        "cUrl": "1",
    }).encode()

    try:
        req = urllib.request.Request(POST_URL, data=form_data, headers={
            **HEADERS, "Content-Type": "application/x-www-form-urlencoded",
        })
        resp = urllib.request.urlopen(req, timeout=15)
        post_result = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"Lỗi kết nối CSGT: {exc}"
        )

    # CAPTCHA sai → retry 1 lần
    if post_result.strip() == "404":
        logger.info("CAPTCHA wrong, retrying...")
        try:
            req = urllib.request.Request(CAPTCHA_URL, headers=HEADERS)
            resp = urllib.request.urlopen(req, timeout=10)
            img_data = resp.read()
            import pytesseract
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            captcha_text = pytesseract.image_to_string(
                img, config="--psm 7 -c tessedit_char_whitelist=0123456789"
            ).strip()
            form_data = urllib.parse.urlencode({
                "BienKS": norm_plate.replace("-", ""),
                "Xe": code,
                "captcha": captcha_text,
                "ipClient": "9.9.9.91",
                "cUrl": "1",
            }).encode()
            req = urllib.request.Request(POST_URL, data=form_data, headers={
                **HEADERS, "Content-Type": "application/x-www-form-urlencoded",
            })
            resp = urllib.request.urlopen(req, timeout=15)
            post_result = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            pass

    if post_result.strip() == "404":
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"⚠️ CAPTCHA không đúng sau 2 lần thử. Vui lòng tra cứu thủ công tại:\n"
            f"{BASE_URL}/tra-cuu-phuong-tien-vi-pham.html"
        )

    # 3) Fetch results page
    try:
        params = urllib.parse.urlencode({"LoaiXe": code, "BienKiemSoat": norm_plate.replace("-", "")})
        req = urllib.request.Request(f"{RESULTS_URL}?{params}", headers=HEADERS)
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        return f"Lỗi lấy kết quả: {exc}"

    # 4) Parse violations
    violations = _parse_violations(html)

    lines = [f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**", ""]

    if not violations:
        lines.append("✅ **Không có vi phạm giao thông nào được ghi nhận.**")
    else:
        lines.append(f"🚨 **Phát hiện {len(violations)} vi phạm:**")
        lines.append("")
        for i, v in enumerate(violations[:20], 1):
            lines.append(f"### Lỗi {i}")
            for key, val in v.items():
                if isinstance(val, list):
                    lines.append(f"- **{key}**:")
                    for item in val:
                        lines.append(f"  - {item.get('name', '')}: {item.get('address', '')}")
                else:
                    lines.append(f"- **{key}**: {val}")
            lines.append("")

    lines.append(f"_Nguồn: Cục CSGT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_")
    return "\n".join(lines)


def _parse_violations(html: str) -> list[dict]:
    """Parse violation data from CSGT results page HTML."""
    soup = BeautifulSoup(html, "html.parser")
    groups = soup.find_all("div", class_="form-group")
    if not groups:
        return []

    violations = []
    current = {}
    places = []

    label_map = {
        "Biển kiểm soát": "licensePlate", "Màu biển": "plateColor",
        "Loại phương tiện": "vehicleType", "Thời gian vi phạm": "violationTime",
        "Địa điểm vi phạm": "violationLocation", "Hành vi vi phạm": "violationBehavior",
        "Trạng thái": "status", "Đơn vị phát hiện vi phạm": "detectionUnit",
    }

    for el in groups:
        # Check if this is a record boundary (<hr>)
        is_boundary = el.find_next("hr") is not None or el.find_previous("hr") is not None

        label_el = el.find("label")
        if not label_el:
            continue

        span = label_el.find("span")
        label_text = span.get_text(strip=True).rstrip(":") if span else label_el.get_text(strip=True).rstrip(":")

        value_el = el.find("div", class_="col-md-9")
        value_text = value_el.get_text(" ", strip=True) if value_el else ""

        # Resolution places (start with "1." or "2.")
        if re.match(r"^\d+\.", label_text.strip()):
            place = {"name": label_text.strip()}
            if "Địa chỉ" in value_text:
                place["address"] = value_text.replace("Địa chỉ:", "").strip()
            places.append(place)
            continue

        # Check if start of new record
        if is_boundary and current:
            if places:
                current["resolutionPlaces"] = places
            violations.append(current)
            current = {}
            places = []

        key = label_map.get(label_text)
        if key and value_text:
            current[key] = value_text

    # Last record
    if current:
        if places:
            current["resolutionPlaces"] = places
        violations.append(current)

    return violations


@mcp.tool()
def list_vehicle_types() -> str:
    """Liệt kê các loại xe được hỗ trợ tra cứu phạt nguội."""
    seen = set()
    out = ["**Loại xe hỗ trợ:**", ""]
    for key, (code, label) in VEHICLE_TYPES.items():
        if label in seen:
            continue
        seen.add(label)
        out.append(f"- {label} (mã {code})")
    return "\n".join(out)
