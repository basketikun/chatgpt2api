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


# Defaults — strongest model (Nano Banana Pro), 16:9 landscape, 1 image per
# request. Override per-call by passing model / aspect_ratio / count.
DEFAULT_MODEL = "NANO_BANANA_PRO"
DEFAULT_TOOL = "PINHOLE"
DEFAULT_ASPECT = "IMAGE_ASPECT_RATIO_LANDSCAPE"
DEFAULT_COUNT = 1
API_HOST = "https://aisandbox-pa.googleapis.com"

# Aspect ratio labels in the Flow UI dropdown (Vietnamese locale).
_ASPECT_LABELS = {
    "IMAGE_ASPECT_RATIO_LANDSCAPE":      "16:9",
    "IMAGE_ASPECT_RATIO_LANDSCAPE_4_3":  "4:3",
    "IMAGE_ASPECT_RATIO_SQUARE":         "1:1",
    "IMAGE_ASPECT_RATIO_PORTRAIT_3_4":   "3:4",
    "IMAGE_ASPECT_RATIO_PORTRAIT":       "9:16",
}

# Flow UI model labels (matches the dropdown text in the screenshot).
# IMPORTANT: Flow's API uses IMAGEN_3_5 internally even though the UI
# shows "Imagen 4" — the user's captured request body confirmed this.
_MODEL_LABELS = {
    "NANO_BANANA_PRO": "Nano Banana Pro",
    "NARWHAL":         "Nano Banana 2",
    "IMAGEN_3_5":      "Imagen 4",
    "IMAGEN_4":        "Imagen 4",  # back-compat alias
}

# When the request interceptor overrides imageModelName, map our friendly
# constants to the actual Flow API enum values. IMAGEN_4 isn't recognized
# by the Flow API — it must be IMAGEN_3_5.
_MODEL_API_VALUE = {
    "NANO_BANANA_PRO": "NANO_BANANA_PRO",
    "NARWHAL":         "NARWHAL",
    "IMAGEN_4":        "IMAGEN_3_5",   # UI alias → real API value
    "IMAGEN_3_5":      "IMAGEN_3_5",
}


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


async def _set_dropdown(page, label_text: str, log_what: str) -> bool:
    """Best-effort: click a Flow UI dropdown button matching `label_text`.

    Flow renders aspect/count/model as pill-style toggle buttons whose
    accessible name matches the visible label ("16:9", "1x", "Nano Banana
    Pro", etc). We click the first one we find. If the dropdown was
    already at that value the click is a no-op (Flow doesn't toggle off).

    Returns True if a click landed, False if no match (we keep going —
    Flow will use the project's last setting).
    """
    if not label_text:
        return False
    candidates = [
        page.get_by_role("button", name=label_text, exact=True),
        page.locator(f"button:has-text('{label_text}')"),
        page.locator(f"[aria-label='{label_text}']"),
    ]
    for loc in candidates:
        try:
            await loc.first.click(timeout=1500)
            logger.info("flow_dropdown_set %s=%s", log_what, label_text)
            return True
        except Exception:
            continue
    logger.warning("flow_dropdown_skip %s=%s (no match — using project default)",
                   log_what, label_text)
    return False


async def generate_image(
    project_id: str,
    prompt: str,
    aspect_ratio: str = DEFAULT_ASPECT,
    model: str = DEFAULT_MODEL,
    count: int = DEFAULT_COUNT,
    tool: str = DEFAULT_TOOL,
    profile: str = "google-fx",
    headless: bool = True,
    timeout: int = 90,
) -> dict:
    """Run the full Flow batchGenerateImages flow and return image refs.

    Args:
        count: 1-4. Flow's UI supports 1x/2x/3x/4x. We best-effort drive
            the dropdown; if Flow stored a different default on the project
            you may get a different number back.

    Returns:
        {
          "images": [{"url"|"data": ..., "mime": ..., "id": ...}, ...],
          "raw":    <full API response>,
          "elapsed_ms": int,
          "model": str,
        }
    """
    count = max(1, min(4, int(count or 1)))
    started = time.time()
    flow_url = f"https://labs.google/fx/vi/tools/flow/project/{project_id}"
    api_url = f"{API_HOST}/v1/projects/{project_id}/flowMedia:batchGenerateImages"

    async with pool.page(profile=profile, headless=headless) as page:
        await _prime_flow_session(page)
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

        # ── Fill the prompt — focus the contenteditable via JS then
        # type via page.keyboard.
        #
        # WHY focus + keyboard, not click + keyboard:
        # On freshly-created projects, Flow shows a "Welcome to Flow"
        # tutorial dialog: a full-viewport DIV overlay (1366x768, role=
        # absent) + a dialog box (role="dialog"). The overlay intercepts
        # MOUSE events but JS .focus() bypasses that — the contenteditable
        # is in the DOM and focusable even when an overlay covers it.
        # page.keyboard.type sends key events to whatever has focus, so
        # the dialog never has to be dismissed at all.
        #
        # Empirically confirmed (ce_count=0 after Escape on a fresh project):
        # pressing Escape RIPS DOWN the Slate editor entirely and it never
        # comes back. So we skip Escape and any other dialog-dismissal —
        # just focus the editor that's already in the DOM and start typing.
        focused = await page.evaluate("""
            () => {
                const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
                // pick the largest visible contenteditable (the prompt input)
                const target = ces
                    .map(e => ({e, w: e.offsetWidth, h: e.offsetHeight}))
                    .filter(x => x.w > 200 && x.h > 0)
                    .sort((a, b) => (b.w * b.h) - (a.w * a.h))[0];
                if (!target) {
                    return {
                        found: false,
                        debug_ce_count: ces.length,
                        debug_dims: ces.map(e => ({w: e.offsetWidth, h: e.offsetHeight, role: e.getAttribute('role')})),
                    };
                }
                target.e.focus();
                // Place caret at end (so subsequent keys append)
                const sel = window.getSelection();
                const range = document.createRange();
                range.selectNodeContents(target.e);
                range.collapse(false);
                sel.removeAllRanges();
                sel.addRange(range);
                return {found: true, w: target.w, h: target.h};
            }
        """)
        if not focused.get("found"):
            raise RuntimeError(
                f"Could not find/focus prompt contenteditable. "
                f"ce_count={focused.get('debug_ce_count')} "
                f"dims={focused.get('debug_dims')}"
            )
        logger.info("flow_prompt_focused w=%d h=%d", focused.get("w", 0), focused.get("h", 0))
        await page.keyboard.type(prompt, delay=10)
        # Give React a tick to register the change.
        await asyncio.sleep(0.5)

        # 2) Intercept the outbound batchGenerateImages POST and rewrite
        # its body so aspect/model/count come from THIS request, not from
        # whatever the project's last dropdown selection happened to be.
        # This is the robust path — DOM clicks (previous approach) miss
        # whenever Flow's React re-skins the pickers, but the API contract
        # is stable. User captured the actual body structure: keys are
        # imageAspectRatio / imageModelName / structuredPrompt.parts[].
        api_pattern = "flowMedia:batchGenerateImages"
        api_model = _MODEL_API_VALUE.get(model, model)

        async def _rewrite_request(route) -> None:
            try:
                original = route.request.post_data_json or {}
                # Some Flow builds wrap the payload in `clientContext`/`request`,
                # so walk shallow to find the keys we want and override in place.
                def _patch(d):
                    if not isinstance(d, dict):
                        return
                    if "imageAspectRatio" in d:
                        d["imageAspectRatio"] = aspect_ratio
                    if "imageModelName" in d:
                        d["imageModelName"] = api_model
                    if "imageCount" in d:
                        d["imageCount"] = count
                    # Flow uses `sampleCount` in some payload variants.
                    if "sampleCount" in d:
                        d["sampleCount"] = count
                _patch(original)
                for v in (original.values() if isinstance(original, dict) else []):
                    _patch(v)
                logger.info("flow_request_rewrite aspect=%s model=%s count=%d",
                            aspect_ratio, api_model, count)
                await route.continue_(post_data=json.dumps(original))
            except Exception as exc:
                logger.warning("flow_request_rewrite_failed: %s — sending original",
                                exc)
                await route.continue_()

        await page.route(f"**/{api_pattern}**", _rewrite_request)

        # 3) Click the "Tạo" submit button. On fresh projects the welcome
        # dialog overlay intercepts mouse clicks, so JS .click() is more
        # reliable — it dispatches the synthetic event directly to the
        # element and bypasses the overlay entirely.
        async def _click_generate() -> None:
            clicked = await page.evaluate("""
                () => {
                    const buttons = Array.from(document.querySelectorAll('button'));
                    // Real submit button has text "arrow_forward\\nTạo"
                    // (Material icon name + label, rendered as two lines).
                    let btn = buttons.find(b => /arrow_forward[\\s\\n]+Tạo/i.test(b.innerText || ''));
                    // Send/Generate label fallbacks (English locale or A/B test)
                    if (!btn) {
                        btn = buttons.find(b => /arrow_forward[\\s\\n]+(Generate|Create|Send|Submit)/i.test(b.innerText || ''));
                    }
                    // Any button with arrow_forward / arrow_upward icon
                    if (!btn) {
                        btn = buttons.find(b => /arrow_(forward|upward)/i.test(b.innerText || ''));
                    }
                    // aria-label probe (in case Google adds one)
                    if (!btn) {
                        btn = buttons.find(b => {
                            const al = (b.getAttribute('aria-label') || '').toLowerCase();
                            return ['tạo', 'create', 'send', 'submit', 'generate'].includes(al);
                        });
                    }
                    if (!btn) {
                        // Last-resort: enumerate visible buttons with text including "Tạo" but NOT "add_2"
                        const taoes = buttons.filter(b => {
                            const t = b.innerText || '';
                            return /Tạo/.test(t) && !/add_2/.test(t);
                        });
                        btn = taoes[taoes.length - 1];
                    }
                    if (!btn) return {clicked: false};
                    btn.click();
                    return {clicked: true, label: btn.getAttribute('aria-label'), text: (btn.innerText || '').slice(0, 50).replace(/\\n/g, '|')};
                }
            """)
            if clicked.get("clicked"):
                logger.info("flow_submit_clicked label=%s text=%s", clicked.get("label"), clicked.get("text"))
                return
            # Last-resort fallback — Ctrl+Enter (some Slate editors map
            # this to submit). Plain Enter inserts a newline in Slate.
            logger.warning("flow_submit: no button found, trying Ctrl+Enter")
            await page.keyboard.press("Control+Enter")

        # 4) Wait for the response — the rewritten request goes out under
        # the page's normal flow (with valid recaptcha + browser headers)
        # but with OUR aspect/model/count substituted.
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


async def _prime_flow_session(page) -> None:
    """Prime the Flow session so subsequent project URLs render the app
    (not the marketing landing page).

    Without this, navigating straight to /tools/flow/project/<id> on a
    just-launched Chrome — even with valid Google login cookies — shows
    Google's marketing CTA page. The session has to be "warmed" by
    visiting /tools/flow root AND clicking through it.

    Empirically verified: passive wait on /tools/flow (even 100s+)
    NEVER converts the marketing landing to the app. The user MUST click
    "Create with Google Flow" to fire Google's entitlement check, which
    then redirects to /project/<auto-uuid> and primes the session for
    all subsequent /project/<id> navigations on the same context.
    """
    try:
        await page.goto(
            "https://labs.google/fx/vi/tools/flow",
            wait_until="domcontentloaded",
            timeout=20_000,
        )
    except Exception as exc:
        logger.warning("flow_prime: goto root failed: %s", exc)
        return

    # Did the actual app load? (PRO badge, Dự án mới, edit project buttons)
    try:
        await page.wait_for_function(
            """() => {
                const els = Array.from(document.querySelectorAll('button,a'));
                return els.some(e => {
                    const t = (e.innerText || e.getAttribute('aria-label') || '').trim();
                    return /^pro$|dự án mới|new project|add_2|chỉnh sửa dự án/i.test(t);
                });
            }""",
            timeout=10_000,
        )
        logger.info("flow_prime: already primed (app shell visible)")
        return
    except Exception:
        pass  # marketing landing — force entitlement check

    # Click "Create with Google Flow" via Playwright locator (real click
    # sequence — much more reliable than el.click() in evaluate because
    # React's event delegation needs proper bubbling).
    try:
        btn = page.locator(
            'button:has-text("Create with Google Flow"), '
            'button:has-text("Tạo bằng Google Flow")'
        ).first
        if await btn.count() == 0:
            logger.warning("flow_prime: marketing button not found")
            return
        await btn.scroll_into_view_if_needed(timeout=3_000)
        await btn.click(timeout=5_000)
        logger.info("flow_prime: clicked 'Create with Google Flow'")
    except Exception as exc:
        logger.warning("flow_prime: click failed: %s", exc)
        return

    # Wait for redirect to /project/<uuid> — Google's entitlement check
    # fires here. If we land on /project/<auto>, session is now primed.
    try:
        await page.wait_for_url("**/project/*", timeout=30_000)
        logger.info("flow_prime: redirected to %s", page.url)
    except Exception as exc:
        logger.warning("flow_prime: no /project/ redirect: %s", exc)


async def get_or_create_project(
    profile: str,
    headless: bool = False,
    timeout: int = 90,
) -> dict[str, Any]:
    """Return the UUID of a Flow project the logged-in account owns,
    creating a fresh one if none exist. The profile MUST already be
    logged in (typically via /v1/session/auto-login or manual noVNC).

    Returns:
        {
          "project_id": "<uuid>",
          "action": "use_existing" | "created",
          "project_count": int,
          "elapsed_ms": int,
        }
    """
    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        # Prime session — handles the marketing-landing detour itself.
        await _prime_flow_session(page)

        # If priming clicked "Create with Google Flow", we may already be
        # on /project/<auto-uuid>. Grab that UUID — it's a perfectly
        # usable existing project.
        import re
        cur = page.url
        m = re.search(r"/project/([0-9a-f-]+)", cur, re.I)
        if m:
            return {
                "project_id": m.group(1),
                "action": "created",  # via warmup click
                "project_count": 0,
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        # Otherwise look for existing project links on /tools/flow root.
        result = await page.evaluate(
            """() => {
                const links = Array.from(document.querySelectorAll('a[href*="/project/"]'))
                    .map(a => (a.href.match(/\\/project\\/([0-9a-f-]+)/i) || [])[1])
                    .filter(Boolean);
                return {existing: links};
            }"""
        )
        existing = result.get("existing", [])
        if existing:
            return {
                "project_id": existing[0],
                "action": "use_existing",
                "project_count": len(existing),
                "elapsed_ms": int((time.time() - started) * 1000),
            }

        # No projects — click "Dự án mới" / "New project" button.
        clicked = await page.evaluate(
            """() => {
                const btn = Array.from(document.querySelectorAll('button')).find(
                    b => /add_2|dự án mới|new project/i.test(
                      b.innerText || b.getAttribute('aria-label') || ''
                    )
                );
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if not clicked:
            raise RuntimeError("Could not find 'Dự án mới' / 'New project' button")

        try:
            await page.wait_for_url("**/project/*", timeout=20_000)
        except Exception as exc:
            raise RuntimeError(
                f"New-project click did not redirect to /project/<uuid> ({exc})"
            ) from exc

        import re
        m = re.search(r"/project/([0-9a-f-]+)", page.url, re.I)
        if not m:
            raise RuntimeError(f"Could not extract UUID from URL: {page.url}")
        return {
            "project_id": m.group(1),
            "action": "created",
            "project_count": 0,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
