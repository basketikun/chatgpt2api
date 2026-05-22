"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam.

Cập nhật 2026: Dùng reCAPTCHA v3 token generation để tra cứu tự động.
Tham khảo từ script của luuquangvu.

API endpoint cũ (csgt.vn) vẫn còn hoạt động cho POST dù GET redirect sang
csgt.bocongan.gov.vn. Sitekey lấy từ trang mới.
"""

from __future__ import annotations

import logging
import re
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)

mcp = FastMCP("vn_phat_nguoi")

# ── Constants ──
CSGT_PAGE = "https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi"
CSGT_API = "https://csgt.bocongan.gov.vn/tra-cuu-vi-pham-qua-hinh-anh"
SITE_KEY = "6LfcU6MsAAAAAF7XE191a3wa4_8B2pr6WJQoims1"  # Fallback, will scrape from page


def _scrape_sitekey() -> str:
    """Lấy sitekey từ trang CSGT."""
    try:
        req = urllib.request.Request(CSGT_PAGE,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")
        for p in [
            r'sitekey\s*[:=]\s*"([^"]+)"',
            r"sitekey\s*[:=]\s*'([^']+)'",
            r'data-sitekey="([^"]+)"',
        ]:
            m = re.search(p, html, re.I)
            if m:
                return m.group(1)
    except Exception:
        pass
    return SITE_KEY

VEHICLE_TYPES = {
    "oto": ("car", "Ô tô"), "ô tô": ("car", "Ô tô"), "car": ("car", "Ô tô"),
    "xemay": ("motorbike", "Xe máy"), "xe máy": ("motorbike", "Xe máy"),
    "motorbike": ("motorbike", "Xe máy"),
    "xedien": ("electricbike", "Xe đạp điện"),
    "xe đạp điện": ("electricbike", "Xe đạp điện"),
    "electricbike": ("electricbike", "Xe đạp điện"),
}

PLATE_PATTERNS = {
    "car": re.compile(r"^\d{2}[A-Z]{1,2}\d{4,5}$"),
    "motorbike": re.compile(r"^\d{2}[A-Z0-9]{1,2}\d{4,5}$"),
    "electricbike": re.compile(r"^\d{2}[A-Z0-9]{1,2}\d{4,5}$"),
}


def _normalise_plate(plate: str) -> str:
    """Chuẩn hóa biển số: 34A47645 → 34A-47645"""
    p = plate.strip().upper().replace(" ", "").replace("-", "")
    if len(p) >= 7:
        # Insert dash: 2 digits + 1-2 letters + rest
        m = re.match(r"^(\d{2}[A-Z]{1,2})(\d{4,5})$", p)
        if m:
            p = f"{m.group(1)}-{m.group(2)}"
    return p


def _is_valid_plate(plate: str, vehicle_type: str = "car") -> bool:
    p = plate.replace("-", "")
    pat = PLATE_PATTERNS.get(vehicle_type, PLATE_PATTERNS["car"])
    return bool(pat.match(p))


# ── reCAPTCHA v3 Token Generation ──

def _get_recaptcha_token(sitekey: str) -> str | None:
    """Generate reCAPTCHA v3 token for CSGT lookup."""
    try:
        # Step 1: Get reCAPTCHA JS version
        js_url = f"https://www.google.com/recaptcha/api.js?render={sitekey}"
        req = urllib.request.Request(js_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        js_text = resp.read().decode("utf-8", errors="ignore")
        ver = re.search(r"release/([A-Za-z0-9_-]+)", js_text)
        version = ver.group(1) if ver else "4Xgct4UibNX93Vrm5g7t5h8F"

        # Step 2: Get anchor token (reCAPTCHA v3 uses anchor too)
        co_b64 = "aHR0cHM6Ly9jc2d0LmJvY29uZ2FuLmdvdi52bjo0NDM"
        anchor_url = (
            f"https://www.google.com/recaptcha/api2/anchor?"
            f"ar=1&k={sitekey}&co={co_b64}&hl=vi&size=invisible&cb=1&v={version}"
        )
        req = urllib.request.Request(anchor_url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        anchor_html = resp.read().decode("utf-8", errors="ignore")
        anchor_token = re.search(r'"recaptcha-token"\s+value="([^"]+)"', anchor_html)
        if not anchor_token:
            # Try v3-specific pattern
            anchor_token = re.search(r'id="recaptcha-token"[^>]*value="([^"]+)"', anchor_html)
        if not anchor_token:
            logger.warning("reCAPTCHA: couldn't find anchor token")
            return None
        token = anchor_token.group(1)

        # Step 3: Reload to get final response token
        reload_url = f"https://www.google.com/recaptcha/api2/reload?k={sitekey}"
        reload_data = urllib.parse.urlencode({
            "c": token, "v": version, "reason": "q", "k": sitekey,
        }).encode()
        req = urllib.request.Request(reload_url, data=reload_data,
            headers={"User-Agent": "Mozilla/5.0", "Content-Type": "application/x-www-form-urlencoded"})
        resp = urllib.request.urlopen(req, timeout=10)
        raw = resp.read().decode("utf-8", errors="ignore")
        raw = re.sub(r"^\)\]}'\s*", "", raw.strip())
        data = json.loads(raw)
        # Flexible parsing
        if isinstance(data, list) and len(data) > 1:
            second = data[1]
            if isinstance(second, str) and len(second) > 100:
                return second
            elif isinstance(second, list) and len(second) >= 2:
                return second[1]
        logger.warning("reCAPTCHA: unexpected response: %s", str(data)[:200])
    except Exception as exc:
        logger.warning("reCAPTCHA failed: %s", exc)
    return None


# ── CSRF Token ──

def _fetch_csrf_token() -> str | None:
    """Lấy CSRF token từ trang tra cứu."""
    try:
        req = urllib.request.Request(CSGT_PAGE,
            headers={"User-Agent": "Mozilla/5.0", "Accept": "text/html"})
        resp = urllib.request.urlopen(req, timeout=10)
        html = resp.read().decode("utf-8", errors="ignore")
        m = re.search(r'name="_token"\s+value="([^"]+)"', html)
        if m:
            return m.group(1)
    except Exception as exc:
        logger.warning("CSRF fetch failed: %s", exc)
    return None


# ── Parsing ──

def _extract_violations(html: str) -> list[dict]:
    """Parse violation cards from HTML response."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.find_all("div", class_="violation-card")
    if not cards:
        return []

    violations = []
    for card in cards:
        v = {}
        title_el = card.find("div", class_="violation-title")
        if title_el:
            v["title"] = title_el.get_text(strip=True)

        status_el = card.find("span", class_=re.compile(r"status"))
        if status_el:
            v["status"] = status_el.get_text(strip=True)

        info_groups = card.find_all("div", class_="info-group")
        for group in info_groups:
            label_el = group.find("span", class_="label")
            value_el = group.find("span", class_="value")
            if label_el and value_el:
                v[label_el.get_text(strip=True)] = value_el.get_text(strip=True)

        if v:
            violations.append(v)
    return violations


# ── Main Tool ──

@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam (tự động qua reCAPTCHA v3).

    Args:
        plate: Biển số xe (vd: "30A-12345", "34A47645").
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

    if not _is_valid_plate(norm_plate, code):
        return (
            f"Biển số '{plate}' không đúng định dạng VN.\n"
            "Định dạng đúng: XX(A-Z)-12345 hoặc 29-K3-1234.56"
        )

    # Get CSRF token
    csrf = _fetch_csrf_token()
    if not csrf:
        # Fallback: return instructions
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"Không lấy được CSRF token. Vui lòng tra cứu thủ công tại:\n"
            f"{CSGT_PAGE}\n\n"
            f"Chọn **{vt_label}**, nhập `{norm_plate}`, xác thực reCAPTCHA, bấm Tra cứu."
        )

    # Get reCAPTCHA token
    sitekey = _scrape_sitekey()
    recaptcha = _get_recaptcha_token(sitekey)
    if not recaptcha:
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"Không thể xác thực reCAPTCHA tự động. Vui lòng tra cứu thủ công tại:\n"
            f"{CSGT_PAGE}\n\n"
            f"Chọn **{vt_label}**, nhập `{norm_plate}`, bấm Tra cứu."
        )

    # POST lookup
    form_data = urllib.parse.urlencode({
        "_token": csrf,
        "g-recaptcha-response": recaptcha,
        "vehicle_type": code,
        "plate_number": norm_plate.replace("-", ""),
    }).encode()

    try:
        req = urllib.request.Request(CSGT_API, data=form_data,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Content-Type": "application/x-www-form-urlencoded",
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/html",
                "Origin": "https://csgt.bocongan.gov.vn",
                "Referer": CSGT_PAGE,
            })
        resp = urllib.request.urlopen(req, timeout=15)
        html = resp.read().decode("utf-8", errors="ignore")
    except Exception as exc:
        logger.warning("CSGT API call failed: %s", exc)
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"Lỗi kết nối đến máy chủ CSGT. Vui lòng thử lại sau hoặc tra cứu tại:\n"
            f"{CSGT_PAGE}"
        )

    # Parse violations
    violations = _extract_violations(html)

    if not violations:
        # Check if HTML says no violations
        if "không có" in html.lower() or "không tìm thấy" in html.lower():
            return (
                f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
                f"✅ **Không có vi phạm giao thông nào được ghi nhận.**\n"
                f"_Nguồn: Cục CSGT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_"
            )
        return (
            f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
            f"⚠️ Không parse được kết quả. Vui lòng tra cứu thủ công tại:\n"
            f"{CSGT_PAGE}"
        )

    lines = [
        f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**",
        "",
    ]
    for i, v in enumerate(violations[:10], 1):
        lines.append(f"### Vi phạm {i}")
        for key, val in v.items():
            lines.append(f"- **{key}**: {val}")
        lines.append("")

    lines.append(f"_Nguồn: Cục CSGT — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_")
    return "\n".join(lines)


@mcp.tool()
def list_vehicle_types() -> str:
    """Liệt kê các loại xe được hỗ trợ tra cứu phạt nguội."""
    seen = set()
    out = ["**Loại xe hỗ trợ tra cứu phạt nguội:**", ""]
    for key, (code, label) in VEHICLE_TYPES.items():
        if label in seen:
            continue
        seen.add(label)
        out.append(f"- {label}")
    out.append("")
    out.append(f"📌 Nguồn: {CSGT_PAGE}")
    return "\n".join(out)
