"""Gemini Web (gemini.google.com) capability handlers.

Reuses the persistent Chrome profile from BrowserPool — caller MUST have
already onboarded the profile via gemini_web_login.start_gemini_web_login.

Capabilities (added incrementally — start with chat, expand later):
  • chat(profile, prompt, timeout) → text response
  • generate_image(profile, prompt) → image URL  [Phase B]
  • analyze_image(profile, prompt, image_url) → text  [Phase C]
  • generate_music(profile, prompt) → audio URL  [Phase D]

DOM scraping approach: type into the contenteditable prompt input, click
Send, wait for the response stream to finish, scrape the assistant text.

Gemini's DOM selectors change with A/B tests, so handlers prefer
attribute-based / text-content matchers and fall back to multiple
candidate selectors.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from ..browser_pool import pool

logger = logging.getLogger(__name__)


_GEMINI_HOME = "https://gemini.google.com/app"

# Selectors for the prompt textarea (contenteditable div in Gemini's React UI).
_PROMPT_INPUT_SELECTORS = (
    'div[contenteditable=true][role=textbox]',
    'rich-textarea div[contenteditable=true]',
    '[contenteditable=true].ql-editor',
    'div.text-input-field div[contenteditable=true]',
)

# Selectors for the Send button.
_SEND_BUTTON_SELECTORS = (
    'button[aria-label*="Send"]',
    'button[aria-label*="Gửi"]',
    'button[mat-icon-button][aria-label*="ubmit"]',
    'send-button button',
)

# Selectors for the assistant response container (where text streams in).
_RESPONSE_SELECTORS = (
    'message-content',
    'model-response message-content',
    '.markdown',
    '.model-response-text',
)


async def _wait_for_ready(page, timeout: int = 30) -> None:
    """Wait for the Gemini app to hydrate (prompt input visible)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready = await page.evaluate("""
            () => {
                const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
                return ces.some(e => e.offsetWidth > 200 && e.offsetHeight > 0);
            }
        """)
        if ready:
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"Gemini app didn't hydrate within {timeout}s")


async def _inject_prompt(page, prompt: str) -> None:
    """Click into the Quill (ql-editor) prompt input + type via keyboard.

    Gemini uses Quill which listens to real keyboard events (not Slate's
    beforeinput). The InputEvent trick we use for Flow's Slate editor
    leaves Quill's internal data model empty — Send button stays
    disabled and submit fires with empty text.

    Sequence:
      1. JS focus + caret placement (works through overlays).
      2. Playwright locator.click() to give Quill a real focus event.
      3. page.keyboard.type — keystrokes that Quill registers.
    """
    # JS focus first (immune to overlays, guarantees the right element).
    ok = await page.evaluate(
        """() => {
            const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
            const target = ces
                .map(e => ({e, w: e.offsetWidth, h: e.offsetHeight}))
                .filter(x => x.w > 200 && x.h > 0)
                .sort((a, b) => (b.w * b.h) - (a.w * a.h))[0];
            if (!target) return false;
            target.e.focus();
            const sel = window.getSelection();
            const range = document.createRange();
            range.selectNodeContents(target.e);
            range.collapse(false);
            sel.removeAllRanges();
            sel.addRange(range);
            return true;
        }"""
    )
    if not ok:
        raise RuntimeError("Could not find/focus Gemini prompt input")

    # Real mouse click to activate Quill's event listeners.
    try:
        await page.locator("rich-textarea div[contenteditable=true], div[contenteditable=true][role=textbox]").first.click(timeout=5000)
    except Exception as exc:
        logger.warning("gemini_web: mouse click into prompt failed: %s — keys may go to wrong target", str(exc)[:120])

    # Type via real keyboard events (Quill listens to these).
    await page.keyboard.type(prompt, delay=10)
    await asyncio.sleep(0.4)


async def _click_send(page) -> bool:
    """Click the Send button — try multiple selectors, fall back to
    JS-dispatched click on any aria-label-marked submit button."""
    for sel in _SEND_BUTTON_SELECTORS:
        try:
            loc = page.locator(sel).first
            await loc.click(timeout=4000)
            logger.info("gemini_web: clicked send via %s", sel)
            return True
        except Exception:
            continue
    # JS fallback — find any button with aria-label containing Send/Gửi
    clicked = await page.evaluate("""
        () => {
            const btn = Array.from(document.querySelectorAll('button')).find(b => {
                const al = (b.getAttribute('aria-label') || '').toLowerCase();
                return /send|gửi|submit/.test(al);
            });
            if (!btn) return false;
            btn.click();
            return true;
        }
    """)
    if clicked:
        logger.info("gemini_web: clicked send via JS fallback")
        return True
    return False


# Text patterns that indicate Gemini is still working (image gen,
# tool call, etc) — don't stop polling when we see these.
_PLACEHOLDER_PATTERNS = (
    "đang tạo",       # "đang tạo hình ảnh", "đang tạo nhạc"
    "đang suy nghĩ",
    "đang xử lý",
    "creating",
    "generating",
    "thinking",
    "gemini đã nói",  # appears WITH placeholder text while still streaming
)


def _is_placeholder(text: str) -> bool:
    """Return True if the text looks like Gemini's 'working' indicator."""
    if not text:
        return True
    t = text.lower().strip()
    if len(t) < 80:  # very short responses are usually placeholders
        return any(p in t for p in _PLACEHOLDER_PATTERNS)
    return False


async def _wait_for_response_complete(page, timeout: int = 90) -> str:
    """Wait for the assistant response to finish streaming, then return its
    text content. Skips past 'Đang tạo / generating' placeholders so the
    caller doesn't get the placeholder as the final result."""
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0
    while time.time() < deadline:
        await asyncio.sleep(1.0)
        text = await page.evaluate(
            """() => {
                const candidates = [
                    'message-content',
                    '.model-response-text',
                    '.markdown',
                    '[data-test-id="response-content"]',
                    'model-response',
                    '.conversation-container .response',
                ];
                for (const sel of candidates) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) {
                        const last = nodes[nodes.length - 1];
                        const text = (last.innerText || '').trim();
                        if (text) return text;
                    }
                }
                return '';
            }"""
        )
        # Don't stop on placeholder text — keep waiting for real content.
        if _is_placeholder(text):
            stable_count = 0
            last_text = text
            continue
        if text and text == last_text:
            stable_count += 1
            if stable_count >= 2:
                return text
        else:
            stable_count = 0
            last_text = text
    if last_text and not _is_placeholder(last_text):
        return last_text
    raise RuntimeError(f"Gemini didn't produce a response within {timeout}s (last text: {last_text!r})")


async def _wait_for_image(page, timeout: int = 120) -> list[str]:
    """Poll the latest message-content for <img> tags, return their URLs.

    Gemini renders generated images as <img src="..."> inside the last
    assistant response. Image gen typically takes 15-40s after submit.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(2.0)
        urls = await page.evaluate(
            """() => {
                // Find the LAST assistant response container.
                const candidates = [
                    'message-content',
                    'model-response',
                    '.model-response-text',
                ];
                let lastResponse = null;
                for (const sel of candidates) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) { lastResponse = nodes[nodes.length - 1]; break; }
                }
                if (!lastResponse) return [];
                // Extract <img> URLs, filtering out tiny icons (< 100px).
                return Array.from(lastResponse.querySelectorAll('img'))
                    .filter(img => img.naturalWidth >= 100 && img.naturalHeight >= 100)
                    .map(img => img.src)
                    .filter(src => src && (src.startsWith('http') || src.startsWith('data:image/')));
            }"""
        )
        if urls and len(urls) > 0:
            return urls
    return []


async def generate_image(
    profile: str,
    prompt: str,
    count: int = 1,
    timeout: int = 120,
    headless: bool = False,
) -> dict[str, Any]:
    """Generate image(s) via gemini.google.com.

    Gemini auto-detects image intent from natural language. We prepend
    a Vietnamese trigger phrase to make the intent unambiguous, then
    wait for <img> tags to appear in the response.

    Returns:
        {
          "images": [{"url": ..., "mime": "image/jpeg"}, ...],
          "elapsed_ms": int,
        }
    """
    # Trigger Imagen by stating image intent explicitly.
    if count > 1:
        full_prompt = f"Tạo cho tôi {count} hình ảnh khác nhau về: {prompt}"
    else:
        full_prompt = f"Tạo cho tôi 1 hình ảnh: {prompt}"

    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_ready(page, timeout=30)

        await _inject_prompt(page, full_prompt)
        await asyncio.sleep(0.4)
        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Gemini Send button")

        urls = await _wait_for_image(page, timeout=timeout)
        if not urls:
            # Maybe Gemini returned text refusal instead — try to read.
            text = await page.evaluate(
                """() => {
                    const n = document.querySelectorAll('message-content');
                    if (!n.length) return '';
                    return (n[n.length-1].innerText || '').slice(0, 300);
                }"""
            )
            raise RuntimeError(
                f"Không có ảnh sinh trong {timeout}s. Gemini có thể từ chối: {text!r}"
            )

        # Detect mime from URL prefix.
        images = []
        for url in urls:
            if url.startswith("data:image/"):
                mime = url.split(";", 1)[0].replace("data:", "")
            else:
                mime = "image/jpeg"  # googleusercontent CDN serves JPEG
            images.append({"url": url, "mime": mime})

        return {
            "images": images,
            "count": len(images),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


async def chat(profile: str, prompt: str, timeout: int = 90, headless: bool = False) -> dict[str, Any]:
    """Send a single prompt to gemini.google.com and return its response.

    Returns:
        {
          "text": <assistant response>,
          "elapsed_ms": int,
        }

    Profile must already be logged in via gemini_web_login.
    Each call opens a fresh chat (no history) — for multi-turn, the
    caller passes the previous messages in `prompt` as serialized text.
    """
    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_ready(page, timeout=30)

        await _inject_prompt(page, prompt)
        await asyncio.sleep(0.4)

        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Gemini Send button")

        text = await _wait_for_response_complete(page, timeout=timeout)
        return {
            "text": text,
            "elapsed_ms": int((time.time() - started) * 1000),
        }
