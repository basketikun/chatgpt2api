"""End-to-end phatnguoi.vn lookup using a real browser.

Cloudflare Turnstile gates every lookup, so we:

1. Reuse the persistent `phatnguoi` profile so cf_clearance cookies survive
   across calls (one-time noVNC click bootstraps this — see /v1/session/manual-login).
2. Load https://phatnguoi.vn/, fill BienKS + Xe radio.
3. Wait for the Turnstile widget to auto-pass (cookie hit, ~1-3 s) or fall
   through the same auto-click / 2captcha fallback chain as solve_turnstile().
4. Submit the form. The server re-renders the same page with the results
   inlined below the form, which we then scrape.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from ..browser_pool import pool
from ..settings import settings
from . import twocaptcha
from .turnstile import _read_token, _try_click_checkbox

logger = logging.getLogger(__name__)

PHATNGUOI_HOME = "https://phatnguoi.vn/"
PHATNGUOI_SITEKEY = "0x4AAAAAADJ42iX8Yvx1UXWe"


async def _ensure_turnstile_token(page) -> dict:
    """Block until we have a Turnstile token in the hidden input.

    Returns metadata about how the token was obtained so the caller can
    surface that in the response for diagnostics.
    """
    # Fast path — cookie auto-pass.
    fast_deadline = time.time() + 6
    while time.time() < fast_deadline:
        if await _read_token(page):
            return {"method": "cookie"}
        await asyncio.sleep(0.4)

    # Try clicking the checkbox if widget shows one.
    if await _try_click_checkbox(page):
        deadline = time.time() + 20
        while time.time() < deadline:
            if await _read_token(page):
                return {"method": "auto_click"}
            await asyncio.sleep(0.5)

    # Final slow poll — Cloudflare sometimes flips after extra fingerprint checks.
    deadline = time.time() + 15
    while time.time() < deadline:
        if await _read_token(page):
            return {"method": "slow"}
        await asyncio.sleep(0.5)

    # 2captcha fallback — inject the token into the hidden input ourselves.
    if twocaptcha.is_enabled():
        logger.info("phatnguoi.vn: falling back to 2captcha")
        result = await twocaptcha.solve_turnstile_2captcha(
            url=PHATNGUOI_HOME, sitekey=PHATNGUOI_SITEKEY
        )
        token = result["token"]
        await page.evaluate(
            """(token) => {
                let inp = document.querySelector("input[name='cf-turnstile-response']");
                if (!inp) {
                    inp = document.createElement('input');
                    inp.type = 'hidden';
                    inp.name = 'cf-turnstile-response';
                    document.querySelector('#tracuu')?.appendChild(inp);
                }
                inp.value = token;
            }""",
            token,
        )
        return {"method": "2captcha", "task_id": result.get("task_id")}

    raise TimeoutError("no turnstile token (no cookie, click failed, 2captcha disabled)")


def _parse_violations(html: str) -> list[dict]:
    """Scrape the violation list rendered into the form's result panel.

    phatnguoi.vn re-renders the SAME page after POST, with the lookup result
    inlined inside #ketquatracuu (or similar). Each violation row uses a
    consistent label → value layout we can pick apart with regex.
    """
    # Strip script/style noise so regex doesn't choke on inline JS.
    html = re.sub(r"<script[\s\S]*?</script>", "", html)
    html = re.sub(r"<style[\s\S]*?</style>", "", html)

    # Each violation block starts with a header like "Lỗi #1" — split on those.
    blocks = re.split(r"L[ỗo]i\s*#\d+", html, flags=re.IGNORECASE)[1:]
    if not blocks:
        return []

    field_patterns = {
        "bienKiemSoat":   r"Bi[ểe]n\s*s[ốo]\s*[:<][^>]*>([^<]+)",
        "mauBien":        r"M[àa]u\s*bi[ểe]n\s*[:<][^>]*>([^<]+)",
        "loaiPhuongTien": r"Lo[ạa]i\s*xe\s*[:<][^>]*>([^<]+)",
        "thoiGianViPham": r"Th[ờo]i\s*gian\s*[:<][^>]*>([^<]+)",
        "diaDiemViPham":  r"Đ[ịi]a\s*đi[ểe]m\s*[:<][^>]*>([^<]+)",
        "hanhViViPham":   r"H[àa]nh\s*vi\s*[:<][^>]*>([^<]+)",
        "trangThai":      r"Tr[ạa]ng\s*th[áa]i\s*[:<][^>]*>([^<]+)",
        "donViPhatHien":  r"Đ[ơo]n\s*v[ịi]\s*ph[áa]t\s*hi[ệe]n\s*[:<][^>]*>([^<]+)",
    }

    out: list[dict] = []
    for block in blocks:
        # Look for state — only blocks that mention "Chưa xử phạt" or "Đã xử phạt"
        # are actual violation records (the page also rerenders the form).
        if not re.search(r"(Ch[ưu]a|Đ[ãa])\s*x[ửu]\s*ph[ạa]t", block, re.IGNORECASE):
            continue
        rec: dict = {}
        for key, pat in field_patterns.items():
            m = re.search(pat, block, re.IGNORECASE)
            if m:
                rec[key] = re.sub(r"\s+", " ", m.group(1)).strip()
        # Nơi giải quyết — multiple addresses are listed as "1.Tổ: ... - 2.Tổ: ..."
        m = re.search(
            r"Đ[ịi]a\s*ch[ỉi]\s*gi[ảa]i\s*quy[ếe]t[:<][^>]*>([^<]+(?:<[^>]+>[^<]+)*)",
            block, re.IGNORECASE,
        )
        if m:
            addresses_raw = re.sub(r"<[^>]+>", " ", m.group(1))
            places = re.split(r"\s*\d+\s*\.\s*T[ổo]:\s*", addresses_raw)
            rec["noiGiaiQuyet"] = [{"ten": p.strip()} for p in places if p.strip()]
        if rec:
            out.append(rec)
    return out


async def lookup_phatnguoi(
    plate: str,
    vehicle_type: int = 1,
    profile: str = "phatnguoi",
    headless: bool = True,
    timeout: int | None = None,
) -> dict:
    """End-to-end form submit + scrape on phatnguoi.vn.

    Args:
        plate: Plate number, dashes stripped (e.g. "99A40201" or "99A-40201").
        vehicle_type: 1=Ô tô, 2=Xe máy, 3=Xe điện.
        profile: Browser profile to reuse (cookies persist across calls).
        headless: True for automated; False to render on Xvfb for noVNC.
    """
    clean_plate = re.sub(r"[\s\-\.]", "", plate).upper()
    started = time.time()

    # Fast-fail: in headless mode, Cloudflare blocks fresh sessions hard.
    # Without prior cf_clearance cookies AND no 2captcha key, the solve will
    # certainly time out at ~25 s. Bail in <100 ms so the caller can move on.
    if headless and not twocaptcha.is_enabled():
        ctx = await pool.get(profile=profile, headless=True)
        cookies = await ctx.cookies("https://phatnguoi.vn/")
        cf_cookies = [c for c in cookies if c.get("name", "").startswith("cf_")]
        if not cf_cookies:
            raise RuntimeError(
                "phatnguoi profile has no Cloudflare clearance cookie; "
                "run POST /v1/session/manual-login with profile='phatnguoi' "
                "and click the Turnstile widget via noVNC once."
            )

    async with pool.page(profile=profile, headless=headless) as page:
        # Listen for the upstream response we care about (the form POST may
        # redirect, but the result is rendered into the same page either way).
        await page.goto(PHATNGUOI_HOME, wait_until="domcontentloaded", timeout=30_000)

        # Fill plate + vehicle type.
        await page.fill("input[name='BienKS']", clean_plate)
        await page.check(f"input[name='Xe'][value='{vehicle_type}']")

        # Ensure we have a Turnstile token before submitting.
        token_meta = await _ensure_turnstile_token(page)

        # Submit by clicking the button (not page.locator('form').submit() —
        # the site uses a JS handler that re-injects state).
        await page.click("#tracuu button[type='submit']")
        try:
            await page.wait_for_load_state("networkidle", timeout=20_000)
        except Exception:
            await asyncio.sleep(2)

        html = await page.content()
        violations = _parse_violations(html)
        # Generic "no violation" detector — the site shows a green box.
        no_violation = bool(re.search(r"ch[ưu]a\s*ghi\s*nh[ậa]n\s*l[ỗo]i", html, re.IGNORECASE))

        return {
            "plate": clean_plate,
            "vehicle_type": vehicle_type,
            "violations": violations,
            "no_violation": no_violation and not violations,
            "turnstile": token_meta,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
