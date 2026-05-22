"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam.

2 nguồn song song:
1. api.phatnguoi.vn — GET request, JSON response, không cần captcha
2. csgt.bocongan.gov.vn — reCAPTCHA v3, nguồn chính thức
"""

from __future__ import annotations
import logging, re, json, time
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("vn_phat_nguoi")

PAGE_URL = "https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi"
FORM_URL = "https://csgt.bocongan.gov.vn/tra-cuu-vi-pham-qua-hinh-anh"
PHATNGUOI_API = "https://api.phatnguoi.vn/tra-cuu/{plate}/{vtype}"

VEHICLE_TYPES = {
    "oto": ("1", "Ô tô"), "ô tô": ("1", "Ô tô"), "car": ("1", "Ô tô"),
    "xemay": ("2", "Xe máy"), "xe máy": ("2", "Xe máy"), "motorbike": ("2", "Xe máy"),
}

BROWSERS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

RETRY_LIMIT = 5
BASE_DELAY = 4


def _normalise_plate(plate: str) -> str:
    p = plate.strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^(\d{2})([A-Z]{1,2})(\d{4,5})$", p)
    if m: return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})([A-Z0-9]{1,2})(\d{4,5})$", p)
    if m: return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return plate


def _lookup_phatnguoi_vn(plate: str, vtype: int) -> tuple[list[dict] | None, str]:
    """Gọi phatnguoi.vn qua playwright (headless browser) để vượt Turnstile."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright chưa được cài"

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto("https://phatnguoi.vn/", timeout=30000, wait_until="domcontentloaded")

            # Fill form
            page.fill("input[name=BienKS]", plate.replace("-", ""))
            # Select vehicle type radio
            vtype_map = {1: "xe-1", 2: "xe-2", 3: "xe-3"}
            radio_id = vtype_map.get(vtype, "xe-1")
            try:
                page.check(f"#{radio_id}")
            except Exception:
                pass

            # Click submit and wait for Turnstile to auto-solve
            page.click("button[type=submit]")
            page.wait_for_timeout(8000)  # Wait for Turnstile + result

            html = page.content()
            browser.close()

            # Parse result
            soup = BeautifulSoup(html, "html.parser")
            title_el = soup.select_one(".pn-result__title")
            notice_el = soup.select_one(".pn-result__notice")
            title = title_el.get_text(strip=True) if title_el else ""
            notice = notice_el.get_text(strip=True) if notice_el else ""

            if "captcha" in notice.lower() or "xác minh" in notice.lower():
                return None, "Turnstile không vượt qua được"

            # Parse violations from result items
            violations = []
            items = soup.select(".pn-result__item")
            for item in items:
                v = {}
                for el in item.select(".pn-result__row"):
                    label_el = el.select_one(".pn-result__label")
                    value_el = el.select_one(".pn-result__value")
                    if label_el and value_el:
                        v[label_el.get_text(strip=True).rstrip(":")] = value_el.get_text(strip=True)
                if v:
                    violations.append(v)

            if violations:
                return violations, ""
            if "không có" in title.lower() or "không tìm thấy" in title.lower():
                return [], title
            return None, f"Không parse được kết quả: {title}"
    except Exception as e:
        logger.warning("phatnguoi playwright: %s", e)
        return None, str(e)[:100]


def _lookup_csgt(plate: str, vtype_code: str) -> tuple[list[dict] | None, str]:
    """Gọi csgt.bocongan.gov.vn — nguồn chính thức, cần reCAPTCHA."""
    import requests
    # Step 1: Get page
    for attempt in range(3):
        try:
            ua = BROWSERS[attempt % len(BROWSERS)]
            r = requests.get(PAGE_URL, headers={
                "User-Agent": ua, "Accept": "text/html",
                "Accept-Language": "vi-VN,vi;q=0.9",
            }, timeout=15)
            html = r.text
            csrf = re.search(r'name="_token"\s+value="([^"]+)"', html)
            sk = re.search(r'data-sitekey="([^"]+)"', html) or re.search(r'sitekey\s*[:=]\s*"([^"]+)"', html)
            if csrf and sk:
                break
            time.sleep(2)
        except Exception:
            time.sleep(2)
    else:
        return None, "Không lấy được dữ liệu trang CSGT (có thể bị chặn IP)"

    csrf_token = csrf.group(1)
    sitekey = sk.group(1)

    # Step 2: reCAPTCHA v3 token
    recaptcha = None
    try:
        s = requests.Session()
        s.headers.update({"User-Agent": BROWSERS[0]})
        js = s.get(f"https://www.google.com/recaptcha/api.js?render={sitekey}", timeout=10).text
        ver = re.search(r"release/([A-Za-z0-9_-]+)", js)
        version = ver.group(1) if ver else "4Xgct4UibNX93Vrm5g7t5h8F"
        co = "aHR0cHM6Ly9jc2d0LmJvY29uZ2FuLmdvdi52bjo0NDM"
        anchor = s.get(f"https://www.google.com/recaptcha/api2/anchor?ar=1&k={sitekey}&co={co}&hl=vi&size=invisible&cb=1&v={version}", timeout=10).text
        at = re.search(r'"recaptcha-token"\s+value="([^"]+)"', anchor)
        if at:
            raw = s.post(f"https://www.google.com/recaptcha/api2/reload?k={sitekey}",
                data={"c": at.group(1), "v": version, "reason": "q", "k": sitekey}, timeout=10).text
            raw = re.sub(r"^\)\]}'\s*", "", raw.strip())
            data = json.loads(raw)
            if isinstance(data, list) and len(data) > 1:
                second = data[1]
                recaptcha = second if isinstance(second, str) and len(second) > 100 else \
                    (second[1] if isinstance(second, list) and len(second) >= 2 else None)
    except Exception:
        pass
    if not recaptcha:
        return None, "Không thể xác thực reCAPTCHA tự động"

    # Step 3: POST form
    try:
        r = s.post(FORM_URL, data={
            "_token": csrf_token, "g-recaptcha-response": recaptcha,
            "vehicle_type": "car" if vtype_code == "1" else "motorbike",
            "plate_number": plate.replace("-", ""),
        }, headers={"X-Requested-With": "XMLHttpRequest", "Referer": PAGE_URL, "User-Agent": BROWSERS[0]}, timeout=20)
        violations = _parse_html(r.text)
        return violations, ""
    except Exception as e:
        return None, f"Lỗi kết nối CSGT: {e}"


def _parse_html(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    FIELD_MAP = {
        "Biển kiểm soát:": "bienKiemSoat", "Màu biển:": "mauBien",
        "Loại phương tiện:": "loaiPhuongTien", "Thời gian vi phạm:": "thoiGianViPham",
        "Địa điểm vi phạm:": "diaDiemViPham", "Hành vi vi phạm:": "hanhViViPham",
        "Trạng thái:": "trangThai", "Đơn vị phát hiện vi phạm:": "donViPhatHien",
    }
    violations, current, places = [], {}, []
    for el in soup.select(".form-group"):
        next_el = el.find_next_sibling(); prev_el = el.find_previous_sibling()
        if ((next_el and next_el.name == "hr") or (prev_el and prev_el.name == "hr")) and current:
            current["noiGiaiQuyet"] = places; violations.append(current)
            current = {}; places = []
        label_el = el.select_one("label span"); value_el = el.select_one(".col-md-9")
        if label_el and value_el:
            label = label_el.get_text(strip=True); value = value_el.get_text(strip=True)
            if label in FIELD_MAP: current[FIELD_MAP[label]] = value
        text = el.get_text(strip=True)
        if text.startswith(("1.", "2.", "3.")): places.append({"ten": text})
        elif text.startswith("Địa chỉ:") and places: places[-1]["diaChi"] = text.replace("Địa chỉ:", "").strip()
    if current: current["noiGiaiQuyet"] = places; violations.append(current)
    return violations


def _format(violations: list, plate: str, label: str, source: str, status: str = "") -> str:
    lines = [f"**Tra cứu phạt nguội cho {label} biển số {plate}:**", ""]
    if status:
        lines.append(f"⏳ _Trạng thái: {status}_")
        lines.append("")
    if not violations:
        lines.append("✅ **Không có vi phạm giao thông nào được ghi nhận.**")
    else:
        lines.append(f"🚨 **Phát hiện {len(violations)} vi phạm:**")
        lines.append("")
        for i, v in enumerate(violations[:20], 1):
            lines.append(f"### Lỗi {i}")
            for label_vn, key in [
                ("Biển kiểm soát", "bienKiemSoat"), ("Màu biển", "mauBien"),
                ("Loại phương tiện", "loaiPhuongTien"), ("Thời gian vi phạm", "thoiGianViPham"),
                ("Địa điểm vi phạm", "diaDiemViPham"), ("Hành vi vi phạm", "hanhViViPham"),
                ("Trạng thái", "trangThai"), ("Đơn vị phát hiện", "donViPhatHien"),
            ]:
                if v.get(key): lines.append(f"- **{label_vn}**: {v[key]}")
            for p in v.get("noiGiaiQuyet", []):
                lines.append(f"- **Nơi giải quyết**: {p.get('ten', '')}")
                if p.get("diaChi"): lines.append(f"  📍 {p['diaChi']}")
            lines.append("")
    lines.append(f"_Nguồn: {source} — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC_")
    return "\n".join(lines)


@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam.

    Args:
        plate: Biển số xe (vd: "99A40201", "34A47645").
        vehicle_type: 'oto' / 'xe máy'. Mặc định oto.
    """
    import requests
    norm_plate = _normalise_plate(plate)
    vt = VEHICLE_TYPES.get(vehicle_type.lower().strip())
    if not vt:
        return f"❌ Loại xe '{vehicle_type}' không hợp lệ.\nChọn: ô tô, xe máy."
    code, vt_label = vt
    vtype_map = {"1": 1, "2": 2}

    # ── phatnguoi.vn với playwright (vượt Turnstile) ──
    violations, status = _lookup_phatnguoi_vn(norm_plate, vtype_map.get(code, 1))
    if violations is not None:
        return _format(violations, norm_plate, vt_label, "phatnguoi.vn", status)

    # ── Thất bại ──
    return (
        f"**Tra cứu phạt nguội cho {vt_label} biển số {norm_plate}:**\n\n"
        f"❌ **Tra cứu thất bại.**\n\n"
        f"{status or 'Không rõ nguyên nhân'}\n\n"
        f"📋 **Tra cứu thủ công:**\n"
        f"- https://phatnguoi.vn\n"
        f"- {PAGE_URL}\n\n"
        f"1. Chọn loại phương tiện: **{vt_label}**\n"
        f"2. Nhập biển số: `{norm_plate}`\n"
        f"3. Giải CAPTCHA → bấm Tra cứu"
    )


@mcp.tool()
def list_vehicle_types() -> str:
    seen = set()
    out = ["**Loại xe hỗ trợ tra cứu phạt nguội:**", ""]
    for key, (code, label) in VEHICLE_TYPES.items():
        if label in seen: continue
        seen.add(label); out.append(f"- {label}")
    out.append("")
    out.append(f"📌 CSGT: {PAGE_URL}")
    out.append(f"📌 phatnguoi.vn: https://phatnguoi.vn")
    return "\n".join(out)
