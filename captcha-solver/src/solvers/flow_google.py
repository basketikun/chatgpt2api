"""Google Labs Flow image generator.

End-to-end: open https://labs.google/fx/vi/tools/flow/project/<id> with the
persistent "google-fx" profile (must be logged in to a Google account), let
the React app initialise, harvest the ya29 OAuth bearer token from the
first outbound googleapis.com request, ask the page's own grecaptcha
runtime for a fresh reCAPTCHA Enterprise token, then POST to
aisandbox-pa.googleapis.com from INSIDE the browser context so Chrome
attaches its proprietary x-browser-validation / x-client-data headers.

Setup is a one-time noVNC login:
  POST /v1/session/manual-login {"profile":"google-fx","url":"https://labs.google/fx/vi/tools/flow"}
After that this function works headlessly until the Google session cookie
naturally expires (typically months).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from ..browser_pool import pool

logger = logging.getLogger(__name__)


# Defaults sourced from the captured browser request.
DEFAULT_MODEL = "NARWHAL"
DEFAULT_TOOL = "PINHOLE"
DEFAULT_ASPECT = "IMAGE_ASPECT_RATIO_LANDSCAPE"
API_HOST = "https://aisandbox-pa.googleapis.com"


def _fingerprint(image_url_obj: dict) -> str:
    """Stable identifier for a returned image so callers can dedupe."""
    for key in ("imageId", "mediaId", "id"):
        v = image_url_obj.get(key)
        if isinstance(v, str) and v:
            return v
    return str(image_url_obj)[:80]


def _extract_image_refs(payload: Any) -> list[dict]:
    """Walk the Flow API response and pull out every "image-like" record.

    Flow's batchGenerateImages response shape (Dec 2026):
        {"media": [
            {"name": "<media-id>", "image": {"generatedImage": {
                "fifeUrl": "https://flow-content.google/image/...",
                "mediaGenerationId": "...", "seed": 12345,
                "aspectRatio": "...", "modelNameType": "NARWHAL", ...
            }}}
        ]}
    We accept any dict that exposes one of the known URL fields or raw bytes.
    """
    out: list[dict] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            url = (
                node.get("fifeUrl")        # primary CDN URL for Flow images
                or node.get("mediaUrl")
                or node.get("imageUrl")
                or node.get("gcsUri")
                or node.get("publicUrl")
                or node.get("url")
            )
            data = node.get("encodedImage") or node.get("imageBytes") or node.get("bytes")
            if url or data:
                out.append({
                    "url": url,
                    "data": data,
                    "mime": node.get("mimeType") or node.get("contentType") or "image/png",
                    "id": node.get("mediaGenerationId") or _fingerprint(node),
                    "seed": node.get("seed"),
                    "model": node.get("modelNameType"),
                    "aspect": node.get("aspectRatio"),
                    "prompt": node.get("prompt"),
                })
                return
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(payload)
    return out


async def _capture_bearer(page, timeout_s: float = 25.0) -> str:
    """Observe outgoing requests and grab the first ya29 OAuth bearer."""
    captured: dict[str, str] = {}

    def _on_request(request) -> None:
        if captured.get("token"):
            return
        try:
            auth = (request.headers.get("authorization") or "").strip()
        except Exception:
            return
        if auth.startswith("Bearer ya29."):
            captured["token"] = auth[len("Bearer "):]
            logger.info(
                "captured ya29 bearer len=%d via %s",
                len(captured["token"]),
                request.url[:80],
            )

    page.on("request", _on_request)

    deadline = time.time() + timeout_s
    # Nudge the page to issue auth-bearing calls if it hasn't already.
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        pass
    while time.time() < deadline:
        if captured.get("token"):
            return captured["token"]
        await asyncio.sleep(0.4)

    raise RuntimeError(
        "Could not capture ya29 token. Profile likely not logged in. "
        "Run POST /v1/session/manual-login with profile='google-fx' and "
        "sign in via the noVNC URL, then retry."
    )


async def _get_recaptcha_token(page, action: str = "flow_generate") -> tuple[str, str]:
    """Call grecaptcha.enterprise.execute() on the page; return (token, sitekey).

    The Flow app loads grecaptcha lazily via a script tag with
    ?render=<sitekey>. If the script hasn't auto-loaded yet, we inject the
    script ourselves so we don't have to wait for the React app to trigger
    the load on its own.
    """
    info = await page.evaluate(
        """async (action) => {
            // Locate sitekey from any of the standard places.
            const findSitekey = () => {
                const el = document.querySelector('[data-sitekey]');
                if (el) return el.getAttribute('data-sitekey');
                for (const s of document.querySelectorAll('script[src*="recaptcha"]')) {
                    const m = s.src.match(/render=([^&]+)/);
                    if (m) return m[1];
                }
                if (window.___grecaptcha_cfg?.clients?.[0]?.K?.K?.sitekey) {
                    return window.___grecaptcha_cfg.clients[0].K.K.sitekey;
                }
                return null;
            };
            const sitekey = findSitekey();
            if (!sitekey) return {error: "sitekey not on page"};

            // If grecaptcha isn't loaded yet, inject the script explicitly.
            if (!window.grecaptcha?.enterprise?.execute) {
                if (!document.querySelector('script[data-cs-injected]')) {
                    const sc = document.createElement('script');
                    sc.src = 'https://www.google.com/recaptcha/enterprise.js?render=' + sitekey;
                    sc.async = true;
                    sc.defer = true;
                    sc.dataset.csInjected = '1';
                    document.head.appendChild(sc);
                }
                // Wait up to 30 s for the runtime to register.
                for (let i = 0; i < 150; i++) {
                    if (window.grecaptcha?.enterprise?.execute) break;
                    await new Promise(r => setTimeout(r, 200));
                }
            }
            if (!window.grecaptcha?.enterprise?.execute) {
                return {error: "grecaptcha.enterprise.execute never registered", sitekey};
            }

            // grecaptcha.enterprise has its own ready() callback that must
            // resolve before execute() will work. Promisify it.
            await new Promise(r => grecaptcha.enterprise.ready(r));

            try {
                const token = await grecaptcha.enterprise.execute(sitekey, { action });
                return {token, sitekey};
            } catch (e) {
                return {error: String(e?.message || e), sitekey};
            }
        }""",
        action,
    )
    if not isinstance(info, dict) or info.get("error"):
        raise RuntimeError(f"reCAPTCHA execute failed: {info}")
    token = info.get("token")
    sitekey = info.get("sitekey", "")
    if not token:
        raise RuntimeError(f"reCAPTCHA returned empty token: {info}")
    return token, sitekey


async def generate_image(
    project_id: str,
    prompt: str,
    aspect_ratio: str = DEFAULT_ASPECT,
    model: str = DEFAULT_MODEL,
    tool: str = DEFAULT_TOOL,
    profile: str = "google-fx",
    headless: bool = True,
    timeout: int = 90,
) -> dict:
    """Run the full Flow batchGenerateImages flow and return image refs.

    Returns:
        {
          "images": [{"url"|"data": ..., "mime": ..., "id": ...}, ...],
          "raw":    <full API response>,
          "elapsed_ms": int,
          "model": str,
        }
    """
    started = time.time()
    flow_url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}"
    api_url = f"{API_HOST}/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(flow_url, wait_until="domcontentloaded", timeout=30_000)

        # Flow renders the prompt input as a contenteditable DIV (not a
        # textarea — the only textarea on the page is the hidden
        # g-recaptcha-response shadow input). Wait for a sizeable
        # contenteditable to appear.
        try:
            await page.wait_for_function(
                """() => {
                    const ces = Array.from(document.querySelectorAll('[contenteditable=\"true\"]'));
                    return ces.some(e => e.offsetWidth > 200 && e.offsetHeight > 0);
                }""",
                timeout=60_000,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Flow UI never hydrated (timeout). Profile may be logged out. "
                f"Re-run /v1/session/manual-login with profile='{profile}'. ({exc})"
            ) from exc

        # 1) Fill the prompt into the largest contenteditable div.
        prompt_input = page.locator(
            "[contenteditable='true']"
        ).first
        await prompt_input.click()
        # contenteditable doesn't accept fill() reliably; type instead.
        await page.keyboard.type(prompt, delay=10)
        # Give React a tick to register the change.
        await asyncio.sleep(0.5)

        # 2) Driving aspect-ratio / model dropdowns is brittle (DOM keeps
        # changing) — for now we accept whatever the project's last setting
        # was. The defaults the user picks once in the UI persist across
        # generations because Flow stores them in the project state.

        # 3) Locate the "Tạo" (Create) submit button — it's an icon button
        # whose accessible name is "Tạo". Multiple "Tạo" elements exist on
        # the page (section heading + submit), so prefer the one that is
        # a real button with a click target.
        api_pattern = "flowMedia:batchGenerateImages"

        async def _click_generate() -> None:
            # Try several locator strategies in order.
            candidates = [
                page.get_by_role("button", name="Tạo", exact=True).last,
                page.locator("button[aria-label='Tạo']").last,
                page.locator("button:has-text('Tạo')").last,
            ]
            for loc in candidates:
                try:
                    await loc.click(timeout=3000)
                    return
                except Exception:
                    continue
            # Fallback — press Enter inside the prompt area.
            await prompt_input.focus()
            await page.keyboard.press("Enter")

        # 4) Intercept the outbound flowMedia:batchGenerateImages POST and
        # wait for the response — that's the real API call the page makes
        # with its own (valid) recaptcha + browser headers.
        try:
            async with page.expect_response(
                lambda r: api_pattern in r.url and r.request.method == "POST",
                timeout=(timeout - 10) * 1000,
            ) as resp_info:
                await _click_generate()
            response = await resp_info.value
        except Exception as exc:
            raise RuntimeError(
                f"Did not observe flowMedia POST within timeout: {exc}"
            ) from exc

        if response.status != 200:
            body_text = await response.text()
            raise RuntimeError(
                f"Flow API {response.status}: {body_text[:500]}"
            )

        payload = await response.json()
        images = _extract_image_refs(payload)
        return {
            "images": images,
            "raw": payload,
            "elapsed_ms": int((time.time() - started) * 1000),
            "model": model,
        }
