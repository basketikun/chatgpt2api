"""vn_phat_nguoi — tra cứu phạt nguội Việt Nam.

Multi-source lookup that runs in parallel to maximize hit rate and minimize
latency:

1. api.checkphatnguoi.vn — fast JSON endpoint (~1s), no captcha. Primary.
2. api.phatnguoi.vn       — secondary. Often rate-limited from server IPs
                            ("Hệ thống đang quá tải" with empty data).

If both backends return empty, we DO NOT claim "no violations" — we tell
the user to check manually, because the upstream may simply be blocking us
or the violation may be very recent and not yet indexed.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import cloudscraper
from fastmcp import FastMCP

logger = logging.getLogger(__name__)
mcp = FastMCP("vn_phat_nguoi")

# ── Endpoints ────────────────────────────────────────────────────────────────
CHECKPN_API = "https://api.checkphatnguoi.vn/phatnguoi"
PHATNGUOI_API = "https://api.phatnguoi.vn/tra-cuu/{plate}/{vtype}"
PHATNGUOI_WEB = "https://phatnguoi.vn/"
CHECKPN_WEB = "https://checkphatnguoi.vn/"

# Each backend gets at most this long before we give up on it.
PER_BACKEND_TIMEOUT = 10.0
# Overall wait — we'll race backends in parallel and stop here.
OVERALL_TIMEOUT = 12.0

VEHICLE_TYPES = {
    "oto": ("1", "Ô tô"),    "ô tô": ("1", "Ô tô"),    "car": ("1", "Ô tô"),
    "xemay": ("2", "Xe máy"), "xe máy": ("2", "Xe máy"), "motorbike": ("2", "Xe máy"),
    "xedien": ("3", "Xe điện"), "xe điện": ("3", "Xe điện"), "ebike": ("3", "Xe điện"),
}

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


# ── Plate normalization ─────────────────────────────────────────────────────

def _normalise_plate(plate: str) -> str:
    p = plate.strip().upper().replace(" ", "").replace("-", "").replace(".", "")
    m = re.match(r"^(\d{2})([A-Z]{1,2})(\d{4,5})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    m = re.match(r"^(\d{2})([A-Z0-9]{1,2})(\d{4,5})$", p)
    if m:
        return f"{m.group(1)}{m.group(2)}-{m.group(3)}"
    return plate.strip().upper()


# ── Shared cloudscraper session (TLS reuse) ─────────────────────────────────

_scraper_lock = threading.Lock()
_scraper: cloudscraper.CloudScraper | None = None


def _get_scraper() -> cloudscraper.CloudScraper:
    global _scraper
    if _scraper is None:
        with _scraper_lock:
            if _scraper is None:
                _scraper = cloudscraper.create_scraper()
    return _scraper


# ── Backend 1: api.checkphatnguoi.vn (primary) ──────────────────────────────

def _lookup_checkphatnguoi(plate: str) -> tuple[list[dict] | None, str]:
    """Return (violations, error). violations=[] means upstream confirmed
    no record; violations=None means lookup failed."""
    try:
        r = _get_scraper().post(
            CHECKPN_API,
            json={"bienso": plate},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "Origin": "https://checkphatnguoi.vn",
                "Referer": "https://checkphatnguoi.vn/",
                "User-Agent": BROWSER_UA,
            },
            timeout=PER_BACKEND_TIMEOUT,
        )
    except Exception as exc:
        return None, f"checkphatnguoi.vn: {exc}"

    if r.status_code != 200:
        return None, f"checkphatnguoi.vn: HTTP {r.status_code}"

    try:
        data = r.json()
    except Exception:
        return None, "checkphatnguoi.vn: invalid JSON"

    if not isinstance(data, dict):
        return None, "checkphatnguoi.vn: unexpected payload"

    status = data.get("status")
    raw = data.get("data")

    # status=1 with non-empty data → real violations
    if status == 1 and isinstance(raw, list) and raw:
        violations: list[dict] = []
        for v in raw:
            if not isinstance(v, dict):
                continue
            violations.append({
                "bienKiemSoat": str(v.get("Biển kiểm soát") or ""),
                "mauBien":      str(v.get("Màu biển") or ""),
                "loaiPhuongTien": str(v.get("Loại phương tiện") or ""),
                "thoiGianViPham": str(v.get("Thời gian vi phạm") or ""),
                "diaDiemViPham":  str(v.get("Địa điểm vi phạm") or ""),
                "hanhViViPham":   str(v.get("Hành vi vi phạm") or ""),
                "trangThai":      str(v.get("Trạng thái") or ""),
                "donViPhatHien":  str(v.get("Đơn vị phát hiện vi phạm") or ""),
                "noiGiaiQuyet":   [{"ten": str(x)} for x in (v.get("Nơi giải quyết vụ việc") or []) if isinstance(x, str)],
            })
        return violations, ""

    # status=0 / data=null → upstream says "no record" (but we cannot fully trust this
    # because new violations may not be indexed yet; the caller marks this clearly).
    if status in (0, "0") and (raw is None or raw == []):
        return [], "checkphatnguoi.vn: chưa ghi nhận"

    return None, f"checkphatnguoi.vn: unexpected status={status!r}"


# ── Backend 2: api.phatnguoi.vn (secondary) ─────────────────────────────────

def _lookup_phatnguoi_vn(plate: str, vtype: int) -> tuple[list[dict] | None, str]:
    """Return (violations, error). Fail-fast: a single attempt with short
    timeout; we no longer sleep-retry because the upstream blocks us with
    a permanent "Hệ thống đang quá tải" message."""
    url = PHATNGUOI_API.format(plate=plate.replace("-", ""), vtype=vtype)
    try:
        r = _get_scraper().get(
            url,
            headers={
                "Accept": "application/json",
                "Origin": "https://phatnguoi.vn",
                "Referer": "https://phatnguoi.vn/",
                "User-Agent": BROWSER_UA,
            },
            timeout=PER_BACKEND_TIMEOUT,
        )
    except Exception as exc:
        return None, f"phatnguoi.vn: {exc}"

    if r.status_code != 200:
        return None, f"phatnguoi.vn: HTTP {r.status_code}"

    try:
        data = r.json()
    except Exception:
        return None, "phatnguoi.vn: invalid JSON"

    if not isinstance(data, dict):
        return None, "phatnguoi.vn: unexpected payload"

    msg = str(data.get("message") or "").lower()
    # Upstream block / rate-limit. Treat as FAILURE so we don't lie about
    # the absence of violations.
    if "quá tải" in msg or "qua tai" in msg or "truy cập website" in msg:
        return None, "phatnguoi.vn: bị chặn (Hệ thống quá tải)"

    raw = data.get("data")
    if data.get("status") and isinstance(raw, list) and raw:
        return [v for v in raw if isinstance(v, dict)], ""

    # status=true with empty list → upstream truly says "no record"
    if data.get("status") and (raw == [] or raw is None):
        return [], "phatnguoi.vn: chưa ghi nhận"

    return None, f"phatnguoi.vn: status={data.get('status')!r} msg={msg[:80]!r}"


# ── Output formatter ────────────────────────────────────────────────────────

def _is_resolved(v: dict) -> bool:
    """A violation is treated as resolved (no longer outstanding) when its
    status field starts with "Đã" — e.g. "Đã xử phạt", "Đã giải quyết".
    The official phatnguoi.vn UI hides these by default, so we follow that
    convention to avoid surfacing year-old paid fines as if they were new.
    """
    status = str(v.get("trangThai") or "").strip()
    return status.startswith("Đã") or status.startswith("Đã ")


def _render_one(idx: int, v: dict) -> list[str]:
    out = [f"### Lỗi {idx}"]
    for vlabel, key in [
        ("Biển kiểm soát", "bienKiemSoat"),
        ("Màu biển",       "mauBien"),
        ("Loại phương tiện", "loaiPhuongTien"),
        ("Thời gian vi phạm", "thoiGianViPham"),
        ("Địa điểm vi phạm",  "diaDiemViPham"),
        ("Hành vi vi phạm",   "hanhViViPham"),
        ("Trạng thái",        "trangThai"),
        ("Đơn vị phát hiện",  "donViPhatHien"),
    ]:
        if v.get(key):
            out.append(f"- **{vlabel}**: {v[key]}")
    for p in v.get("noiGiaiQuyet") or []:
        if isinstance(p, dict):
            out.append(f"- **Nơi giải quyết**: {p.get('ten', '')}")
            if p.get("diaChi"):
                out.append(f"  📍 {p['diaChi']}")
        elif isinstance(p, str):
            out.append(f"- **Nơi giải quyết**: {p}")
    out.append("")
    return out


def _format_violations(violations: list[dict], plate: str, label: str, sources: list[str]) -> str:
    """Render results, separating OUTSTANDING (chưa xử phạt) from RESOLVED
    (đã xử phạt) so users get the same "✓ chưa ghi nhận" experience that
    the official phatnguoi.vn site gives when only paid records exist."""
    src = ", ".join(sources) if sources else "phatnguoi.vn"
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"**Tra cứu phạt nguội cho {label} biển số {plate}:**", ""]

    outstanding = [v for v in violations if not _is_resolved(v)]
    resolved = [v for v in violations if _is_resolved(v)]

    if not outstanding:
        # Same wording the official phatnguoi.vn website uses.
        lines.append("✅ **Chúc mừng, chưa ghi nhận lỗi vi phạm chưa xử lý.**")
        if resolved:
            lines.append("")
            lines.append(
                f"_Lịch sử: có {len(resolved)} vi phạm cũ đã được xử lý "
                "(không cần xử lý lại). Xem chi tiết bên dưới nếu cần._"
            )
            lines.append("")
            lines.append("<details>")
            lines.append("<summary>Lịch sử vi phạm đã xử lý</summary>")
            lines.append("")
            for i, v in enumerate(resolved[:20], 1):
                lines.extend(_render_one(i, v))
            lines.append("</details>")
    else:
        lines.append(f"🚨 **Phát hiện {len(outstanding)} vi phạm chưa xử lý:**")
        lines.append("")
        for i, v in enumerate(outstanding[:20], 1):
            lines.extend(_render_one(i, v))
        if resolved:
            lines.append(
                f"_Ngoài ra có {len(resolved)} vi phạm cũ đã được xử lý — bỏ qua._"
            )
            lines.append("")

    lines.append(f"_Nguồn: {src} — {ts}_")
    return "\n".join(lines)


def _format_no_data_with_caveat(plate: str, label: str, sources_tried: list[str], errors: list[str]) -> str:
    """Returned when ALL sources came back empty/failed. We deliberately do
    NOT say "no violations" because some upstreams block us, and some new
    violations may not be indexed yet."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"**Tra cứu phạt nguội cho {label} biển số {plate}:**",
        "",
        "⚠️ **Không tìm thấy vi phạm trong các nguồn API tự động** "
        "(các API này có thể bị chặn hoặc chưa cập nhật vi phạm mới nhất).",
        "",
        "📋 Vui lòng kiểm tra thủ công để chắc chắn:",
        f"- {PHATNGUOI_WEB}",
        f"- {CHECKPN_WEB}",
        f"- https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi",
        "",
        f"1. Chọn loại phương tiện: **{label}**",
        f"2. Nhập biển số: `{plate}`",
        f"3. Giải CAPTCHA → bấm Tra cứu",
        "",
    ]
    if errors:
        lines.append(f"_Chi tiết: {' | '.join(errors[:3])}_")
    lines.append(f"_Đã thử nguồn: {', '.join(sources_tried)} — {ts}_")
    return "\n".join(lines)


# ── Public tool ─────────────────────────────────────────────────────────────

@mcp.tool()
def check_traffic_violation(plate: str, vehicle_type: str = "oto") -> str:
    """Tra cứu phạt nguội xe tại Việt Nam.

    Args:
        plate: Biển số xe (vd: "99A40201", "34A47645").
        vehicle_type: 'oto' / 'xe máy' / 'xe điện'. Mặc định oto.
    """
    norm_plate = _normalise_plate(plate)
    vt = VEHICLE_TYPES.get(vehicle_type.lower().strip())
    if not vt:
        return f"❌ Loại xe '{vehicle_type}' không hợp lệ.\nChọn: ô tô, xe máy, xe điện."
    vt_code_str, vt_label = vt
    vt_code = int(vt_code_str)

    # Race both backends in parallel.
    confirmed_violations: list[dict] = []
    confirmed_sources: list[str] = []
    empty_sources: list[str] = []
    errors: list[str] = []
    seen_keys: set[str] = set()

    def _add_violations(vs: list[dict], src: str) -> None:
        added = 0
        for v in vs:
            key = (
                f"{v.get('thoiGianViPham','')}|"
                f"{v.get('diaDiemViPham','')}|"
                f"{v.get('hanhViViPham','')}"
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            confirmed_violations.append(v)
            added += 1
        if added > 0 and src not in confirmed_sources:
            confirmed_sources.append(src)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_lookup_checkphatnguoi, norm_plate): "checkphatnguoi.vn",
            pool.submit(_lookup_phatnguoi_vn, norm_plate, vt_code): "phatnguoi.vn",
        }
        try:
            for fut in as_completed(futures, timeout=OVERALL_TIMEOUT):
                src = futures[fut]
                try:
                    violations, err = fut.result()
                except Exception as exc:
                    errors.append(f"{src}: {exc}")
                    continue
                if violations is None:
                    errors.append(err or f"{src}: unknown error")
                elif violations:
                    _add_violations(violations, src)
                else:
                    empty_sources.append(src)
        except Exception as exc:
            errors.append(f"timeout: {exc}")

    if confirmed_violations:
        return _format_violations(confirmed_violations, norm_plate, vt_label, confirmed_sources)

    # Both came back empty AND at least one of them WAS reachable → likely
    # truly no record. Still add a caveat because new violations take time
    # to index.
    if empty_sources and not errors:
        return _format_violations([], norm_plate, vt_label, empty_sources) + (
            "\n\n_Lưu ý: vi phạm mới có thể chưa được cập nhật. Nếu cần chắc chắn, kiểm tra thủ công tại https://phatnguoi.vn._"
        )

    # Mixed: at least one source said empty, others errored → soft no-data
    if empty_sources:
        tried = sorted(set(empty_sources + [futures[f] for f in futures]))
        return _format_no_data_with_caveat(norm_plate, vt_label, tried, errors)

    # All sources failed
    return _format_no_data_with_caveat(
        norm_plate, vt_label, [futures[f] for f in futures], errors
    )


@mcp.tool()
def list_vehicle_types() -> str:
    seen: set[str] = set()
    out = ["**Loại xe hỗ trợ tra cứu phạt nguội:**", ""]
    for _key, (_code, label) in VEHICLE_TYPES.items():
        if label in seen:
            continue
        seen.add(label)
        out.append(f"- {label}")
    out.append("")
    out.append(f"📌 phatnguoi.vn: {PHATNGUOI_WEB}")
    out.append(f"📌 checkphatnguoi.vn: {CHECKPN_WEB}")
    out.append("📌 CSGT: https://csgt.bocongan.gov.vn/tra-cuu-phat-nguoi")
    return "\n".join(out)
