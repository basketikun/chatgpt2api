"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam qua bocongan.gov.vn.

API chính thức Cục CSGT:
1. GET trang tra cứu → lấy CSRF token + sitekey
2. Tạo reCAPTCHA v3 token (3-step Google API)
3. POST form → parse kết quả HTML
"""

from __future__ import annotations

import logging, re, io, json, urllib.request, urllib.parse
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("vn_phat_nguoi")

# ── Constants ──
PAGE_URL = "https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi"
FORM_URL = "https://csgt.bocongan.gov.vn/tra-cuu-vi-pham-qua-hinh-anh"

VEHICLE_TYPES = {
    "oto": ("1", "Ô tô"), "ô tô": ("1", "Ô tô"), "car": ("1", "Ô tô"),
    "xemay": ("2", "Xe máy"), "xe máy": ("2", "Xe máy"), "motorbike": ("2", "Xe máy"),
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def _normalise_plate(plate: str) -> str:
    p = plate.strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^(\d{2})([A-Z]{1,2})(\d{4,5})$", p)
    if m: return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})([A-Z0-9]{1,2})(\d{4,5})$", p)
    if m: return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return plate


def _fetch_page() -> tuple[str | None, str | None]:
    """Get CSRF token + sitekey from page (with retry)."""
    import requests, time
    for attempt in range(3):
        try:
            r = requests.get(PAGE_URL, headers={
                **HEADERS, "Accept": "text/html", "Accept-Language": "vi-VN,vi;q=0.9",
            }, timeout=15)
            html = r.text
            csrf = re.search(r'name="_token"\s+value="([^"]+)"', html)
            sk = re.search(r'data-sitekey="([^"]+)"', html) or re.search(r'sitekey\s*[:=]\s*"([^"]+)"', html)
            if csrf and sk:
                return csrf.group(1), sk.group(1)
            logger.info("Page fetch attempt %d: csrf=%s sitekey=%s", attempt+1, bool(csrf), bool(sk))
            time.sleep(1 + attempt)
        except Exception as e:
            logger.warning("Page fetch attempt %d: %s", attempt+1, e)
            time.sleep(2)
    return None, None


def _get_recaptcha_token(sitekey: str) -> str | None:
    """Generate reCAPTCHA v3 token."""
    try:
        import requests
        s = requests.Session()
        s.headers.update(HEADERS)
        # Step 1: version
        js = s.get(f"https://www.google.com/recaptcha/api.js?render={sitekey}", timeout=10).text
        ver = re.search(r"release/([A-Za-z0-9_-]+)", js)
        version = ver.group(1) if ver else "4Xgct4UibNX93Vrm5g7t5h8F"
        # Step 2: anchor
        co = "aHR0cHM6Ly9jc2d0LmJvY29uZ2FuLmdvdi52bjo0NDM"
        anchor = s.get(f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={sitekey}&co={co}&hl=vi&size=invisible&cb=1&v={version}", timeout=10).text
        anchor_token = re.search(r'"recaptcha-token"\s+value="([^"]+)"', anchor)
        if not anchor_token: return None
        token = anchor_token.group(1)
        # Step 3: reload
        reload_data = {"c": token, "v": version, "reason": "q", "k": sitekey}
        raw = s.post(f"https://www.google.com/recaptcha/api2/reload?k={sitekey}", data=reload_data, timeout=10).text
        raw = re.sub(r"^\)\]}'\s*", "", raw.strip())
        data = json.loads(raw)
        if isinstance(data, list) and len(data) > 1:
            second = data[1]
            if isinstance(second, str) and len(second) > 100: return second
            if isinstance(second, list) and len(second) >= 2: return second[1]
    except Exception as e:
        logger.warning("reCAPTCHA: %s", e)
    return None


def _parse_violations(html: str) -> list[dict]:
    """Parse violations from result HTML."""
    soup = BeautifulSoup(html, "html.parser")
    FIELD_MAP = {
        "Biển kiểm soát:" : "bienKiemSoat", "Màu biển:": "mauBien",
        "Loại phương tiện:": "loaiPhuongTien", "Thời gian vi phạm:": "thoiGianViPham",
        "Địa điểm vi phạm:": "diaDiemViPham", "Hành vi vi phạm:": "hanhViViPham",
        "Trạng thái:": "trangThai", "Đơn vị phát hiện vi phạm:": "donViPhatHien",
    }
    violations, current, places = [], {}, []
    for el in soup.select(".form-group"):
        next_el = el.find_next_sibling(); prev_el = el.find_previous_sibling()
        if ((next_el and next_el.name == "hr") or (prev_el and prev_el.name == "hr")) and current:
            current["noiGiaiQuyet"] = places; violations.append(current); current = {}; places = []
        label_el = el.select_one("label span"); value_el = el.select_one(".col-md-9")
        if label_el and value_el:
            label = label_el.get_text(strip=True); value = value_el.get_text(strip=True)
            if label in FIELD_MAP: current[FIELD_MAP[label]] = value
        text = el.get_text(strip=True)
        if text.startswith(("1.", "2.", "3.")): places.append({"ten": text})
        elif text.startswith("Địa chỉ:") and places: places[-1]["diaChi"] = text.replace("Địa chỉ:", "").strip()
    if current: current["noiGiaiQuyet"] = places; violations.append(current)
    return violations


def _format(violations: list, plate: str, label: str, source: str = "CSGT") -> str:
    lines = [f"**Tra cứu phạt nguội cho {label} biển số {plate}:**", ""]
    if not violations:
        lines.append("✅ **Không có vi phạm giao thông nào được ghi nhận.**")
    else:
        lines.append(f"🚨 **Phát hiện {len(violations)} vi phạm:**"); lines.append("")
        for i, v in enumerate(violations[:20], 1):
            lines.append(f"### Lỗi {i}")
            for label_vn, key in [("Biển kiểm soát","bienKiemSoat"),("Màu biển","mauBien"),
                ("Loại phương tiện","loaiPhuongTien"),("Thời gian vi phạm","thoiGianViPham"),
                ("Địa điểm vi phạm","diaDiemViPham"),("Hành vi vi phạm","hanhViViPham"),
                ("Trạng thái","trangThai"),("Đơn vị phát hiện","donViPhatHien")]:
                if v.get(key): lines.append(f"- **{label_vn}**: {v[key]}")
            for p in v.get("noiGiaiQuyet", []):
                lines.append(f"- **Nơi giải quyết**: {p.get('ten','')}")
                if p.get("diaChi"): lines.append(f"  Địa chỉ: {p['diaChi']}")
            lines.append("")
    lines.append(f"_Nguồn: Cục {source} — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_")
    return "\n".join(lines)


@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam qua bocongan.gov.vn.

    Args:
        plate: Biển số xe (vd: "34A47645", "99A40201").
        vehicle_type: 'oto' / 'xe máy'. Mặc định oto.
    """
    import requests
    norm_plate = _normalise_plate(plate)
    vt = VEHICLE_TYPES.get(vehicle_type.lower().strip())
    if not vt: return f"Loại xe '{vehicle_type}' không hợp lệ."
    code, vt_label = vt

    csrf, sitekey = _fetch_page()
    if not csrf or not sitekey:
        # Fallback: try phatnguoi.vn API (simpler, no captcha)
        import requests as req_lib, json as _json
        vtype_map = {"1": 1, "2": 2}
        pn_url = f"https://api.phatnguoi.vn/tra-cuu/{norm_plate.replace('-', '')}/{vtype_map.get(code, 1)}"
        try:
            r = req_lib.get(pn_url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                data = _json.loads(r.text)
                if data.get("status") and isinstance(data.get("data"), list):
                    v_list = [v for v in data["data"] if isinstance(v, dict)]
                    if v_list:
                        return _format(v_list, norm_plate, vt_label, "phatnguoi.vn")
                msg = str(data.get("message", "")).lower()
                if "thành công" in msg or "success" in msg:
                    return _format([], norm_plate, vt_label, "phatnguoi.vn")
        except Exception:
            pass
        return (f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
                f"⚠️ CSGT đang chặn IP. Vui lòng thử lại sau hoặc tra cứu thủ công:\n{PAGE_URL}")

    recaptcha = _get_recaptcha_token(sitekey)
    if not recaptcha:
        # Fallback: manual instructions
        return (f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
                f"⚠️ Không thể xác thực tự động. Vui lòng tra cứu thủ công tại:\n{PAGE_URL}")

    # POST form
    try:
        s = requests.Session(); s.headers.update(HEADERS)
        r = s.post(FORM_URL, data={
            "_token": csrf, "g-recaptcha-response": recaptcha,
            "vehicle_type": "car" if code == "1" else "motorbike",
            "plate_number": norm_plate.replace("-", ""),
        }, headers={"X-Requested-With": "XMLHttpRequest", "Referer": PAGE_URL}, timeout=20)
        violations = _parse_violations(r.text)
        return _format(violations, norm_plate, vt_label, "CSGT")
    except Exception as e:
        return f"Lỗi kết nối CSGT: {e}"


@mcp.tool()
def list_vehicle_types() -> str:
    seen = set(); out = ["**Loại xe hỗ trợ:**", ""]
    for key, (code, label) in VEHICLE_TYPES.items():
        if label in seen: continue
        seen.add(label); out.append(f"- {label}")
    return "\n".join(out)
