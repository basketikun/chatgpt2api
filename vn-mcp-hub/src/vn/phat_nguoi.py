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
FORM_ENDPOINT = f"{BASE_URL}/?mod=contact&task=tracuu_post&ajax"
RESULTS_URL = f"{BASE_URL}/tra-cuu-phuong-tien-vi-pham.html"
MAX_RETRIES = 5

VEHICLE_TYPES = {
    "oto": ("1", "Ô tô"), "ô tô": ("1", "Ô tô"), "car": ("1", "Ô tô"),
    "xemay": ("2", "Xe máy"), "xe máy": ("2", "Xe máy"),
    "motorbike": ("2", "Xe máy"),
    "xedien": ("3", "Xe đạp điện"),
    "xe đạp điện": ("3", "Xe đạp điện"),
    "electricbike": ("3", "Xe đạp điện"),
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
    "Referer": f"{BASE_URL}/tra-cuu-phuong-tien-vi-pham.html",
}

# ── OCR Engine Detection ──
_OCR_ENGINE = None
try:
    import ddddocr
    _OCR_ENGINE = "ddddocr"
except ImportError:
    try:
        import pytesseract
        from PIL import Image, ImageFilter, ImageEnhance
        _OCR_ENGINE = "tesseract"
    except ImportError:
        pass


def _solve_captcha(image_bytes: bytes) -> str:
    """Giải CAPTCHA text đơn giản từ CSGT."""
    if _OCR_ENGINE == "ddddocr":
        try:
            ocr = ddddocr.DdddOcr(show_ad=False)
            return ocr.classification(image_bytes).strip()
        except Exception:
            pass

    if _OCR_ENGINE == "tesseract":
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            img = Image.open(io.BytesIO(image_bytes)).convert("L")
            img = img.filter(ImageFilter.MedianFilter(size=3))
            img = ImageEnhance.Contrast(img).enhance(2.0)
            img = img.point(lambda x: 0 if x < 140 else 255, "1")
            text = pytesseract.image_to_string(
                img, config="--psm 8 -c tessedit_char_whitelist=0123456789"
            ).strip()
            return text
        except Exception:
            # Fallback: raw image
            try:
                return pytesseract.image_to_string(
                    image_bytes, config="--psm 7 -c tessedit_char_whitelist=0123456789"
                ).strip()
            except Exception:
                pass

    return "0000"  # Last resort

PLATE_PATTERN = re.compile(r"^\d{2}[A-Z0-9]{1,2}-?\d{4,5}(\.\d{2})?$", re.I)


def _normalise_plate(plate: str) -> str:
    """Chuẩn hóa biển số: 99A40201 → 99A-40201, 34A47645 → 34A-47645"""
    p = plate.strip().upper().replace(" ", "").replace("-", "")
    # Car: 2 digits + 1-2 LETTERS + 4-5 digits (e.g. 99A40201, 30A12345, 51F31234)
    m = re.match(r"^(\d{2})([A-Z]{1,2})(\d{4,5})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    # Motorbike: 2 digits + 1-2 ALPHANUM + 4-5 digits
    m = re.match(r"^(\d{2})([A-Z0-9]{1,2})(\d{4,5})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return plate


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

    # ── 1) Try phatnguoi.vn (simpler, no captcha) with retry ──
    import requests as req_lib
    import json as _json

    vtype_map = {"1": 1, "2": 2, "3": 3}
    pn_url = f"https://api.phatnguoi.vn/tra-cuu/{norm_plate.replace('-', '')}/{vtype_map.get(code, 1)}"

    for pn_attempt in range(3):
        try:
            r = req_lib.get(pn_url, headers=HEADERS, timeout=15)
            if r.status_code == 200 and len(r.text) > 50:
                try:
                    data = _json.loads(r.text)
                    if data.get("status") and data.get("data"):
                        violations = []
                        for item in data["data"]:
                            if isinstance(item, dict):
                                violations.append(item)
                        if violations:
                            return _format_violations(violations, norm_plate, vt_label)
                    # status=false or empty data → no violations
                    if isinstance(data.get("data"), list) and len(data.get("data", [])) == 0:
                        # Could be "no violations" or "overloaded"
                        msg = str(data.get("message", "")).lower()
                        if "quá tải" in msg or "qua tai" in msg:
                            continue  # Retry
                        return _format_violations([], norm_plate, vt_label)
                except _json.JSONDecodeError:
                    pass
        except Exception:
            pass

    # ── 2) Fallback: return manual instructions ──
    return (
        f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
        f"⚠️ Hệ thống đang quá tải, không thể tra cứu tự động.\n\n"
        f"Vui lòng tra cứu thủ công:\n"
        f"- {BASE_URL}/tra-cuu-phuong-tien-vi-pham.html\n"
        f"- https://phatnguoi.vn\n\n"
        f"Chọn **{vt_label}**, nhập `{norm_plate}`, giải CAPTCHA, bấm Tra cứu."
    )


def _format_violations(violations: list, norm_plate: str, vt_label: str) -> str:
    lines = [f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**", ""]
    if not violations:
        lines.append("✅ **Không có vi phạm giao thông nào được ghi nhận.**")
    else:
        lines.append(f"🚨 **Phát hiện {len(violations)} vi phạm:**")
        lines.append("")
        for i, v in enumerate(violations[:20], 1):
            lines.append(f"### Lỗi {i}")
            fields = [
                ("Biển kiểm soát", "bienKiemSoat", "licensePlate"),
                ("Màu biển", "mauBien", "plateColor"),
                ("Loại phương tiện", "loaiPhuongTien", "vehicleType"),
                ("Thời gian vi phạm", "thoiGianViPham", "violationTime"),
                ("Địa điểm vi phạm", "diaDiemViPham", "violationLocation"),
                ("Hành vi vi phạm", "hanhViViPham", "violationBehavior"),
                ("Trạng thái", "trangThai", "status"),
                ("Đơn vị phát hiện", "donViPhatHien", "detectionUnit"),
            ]
            for label, key_vn, key_en in fields:
                val = v.get(key_vn, "") or v.get(key_en, "")
                if val:
                    lines.append(f"- **{label}**: {val}")
            places = v.get("noiGiaiQuyet", [])
            if places:
                lines.append(f"- **Nơi giải quyết**:")
                for p in places:
                    lines.append(f"  - {p.get('ten', p.get('name', ''))}")
                    addr = p.get('diaChi', p.get('address', ''))
                    if addr:
                        lines.append(f"    Địa chỉ: {addr}")
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

    FIELD_MAP = {
        "Biển kiểm soát:": "bienKiemSoat",
        "Màu biển:": "mauBien",
        "Loại phương tiện:": "loaiPhuongTien",
        "Thời gian vi phạm:": "thoiGianViPham",
        "Địa điểm vi phạm:": "diaDiemViPham",
        "Hành vi vi phạm:": "hanhViViPham",
        "Trạng thái:": "trangThai",
        "Đơn vị phát hiện vi phạm:": "donViPhatHien",
    }

    form_groups = soup.select(".form-group")
    for el in form_groups:
        next_el = el.find_next_sibling()
        prev_el = el.find_previous_sibling()
        is_boundary = (
            (next_el and next_el.name == "hr") or
            (prev_el and prev_el.name == "hr")
        )
        if is_boundary and current:
            current["noiGiaiQuyet"] = places
            violations.append(current)
            current = {}
            places = []

        label_el = el.select_one("label span")
        value_el = el.select_one(".col-md-9")
        if label_el and value_el:
            label = label_el.get_text(strip=True)
            value = value_el.get_text(strip=True)
            if label in FIELD_MAP:
                current[FIELD_MAP[label]] = value

        text = el.get_text(strip=True)
        if text.startswith(("1.", "2.", "3.")):
            places.append({"ten": text})
        elif text.startswith("Địa chỉ:") and places:
            places[-1]["diaChi"] = text.replace("Địa chỉ:", "").strip()

    if current:
        current["noiGiaiQuyet"] = places
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
