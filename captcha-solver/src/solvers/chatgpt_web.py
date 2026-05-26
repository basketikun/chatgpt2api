"""ChatGPT Web (chatgpt.com) capability handlers.

Same DOM-scrape approach as gemini_web.py, but for chatgpt.com:
  • chat()           — send prompt, scrape response
  • generate_image() — activate '+' menu → 'Tạo hình ảnh' tool → prompt
                       → scrape <img>
  • analyze_image()  — upload image via file_chooser → ask question
                       → scrape response

Profile MUST be logged in (typically via chatgpt_login.start_chatgpt_login
or by reusing a profile that already has chatgpt.com cookies). Reuses
the persistent browser context.

ChatGPT Free supports:
  • Chat (no limit on prompt size)
  • DALL-E image gen (3 images/day on free tier)
  • GPT vision (paste/upload image, ask)
NOT supported: music, deep research (paid only).
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import tempfile
import time
from typing import Any

import httpx

from ..browser_pool import pool

logger = logging.getLogger(__name__)


_CHATGPT_HOME = "https://chatgpt.com/"

# Composer prompt input — chatgpt.com uses a ProseMirror-based contenteditable.
_PROMPT_SELECTORS = (
    'div[contenteditable=true]#prompt-textarea',
    'div[contenteditable=true].ProseMirror',
    'div[contenteditable=true][translate="no"]',
    'div[contenteditable=true]',
)
# Send button.
_SEND_SELECTORS = (
    'button[data-testid="send-button"]',
    'button[aria-label*="Send"]',
    'button[aria-label*="Gửi"]',
)
# '+' / 'Thêm' menu trigger.
_PLUS_SELECTORS = (
    'button[aria-label="Thêm"]',
    'button[aria-label="Add"]',
    'button[aria-label*="Attach"]',
    'button[aria-label*="upload"]',
    'button[data-testid="composer-plus-btn"]',
)
# Response container for assistant text.
_RESPONSE_SELECTORS = (
    '[data-message-author-role="assistant"]',
    'article:has([data-message-author-role="assistant"])',
    '.markdown.prose',
    '.message-content',
)

# Patterns that indicate ChatGPT is still working — keep waiting past these.
_PLACEHOLDER_PATTERNS = (
    "đang tạo",
    "generating",
    "thinking",
    "creating",
    "đang suy nghĩ",
    "đang xử lý",
)


def _is_placeholder(text: str) -> bool:
    if not text:
        return True
    t = text.lower().strip()
    if len(t) < 60:
        return any(p in t for p in _PLACEHOLDER_PATTERNS)
    return False


async def _wait_for_ready(page, timeout: int = 30) -> None:
    """Wait for chatgpt.com composer to hydrate."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        ready = await page.evaluate(
            """() => {
                if (document.getElementById('prompt-textarea')) return true;
                const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
                return ces.some(e => e.offsetWidth > 50 && e.offsetHeight > 0);
            }"""
        )
        if ready:
            return
        await asyncio.sleep(0.5)
    raise RuntimeError(f"ChatGPT app didn't hydrate within {timeout}s")


async def _inject_prompt(page, prompt: str) -> None:
    """Focus prompt + real mouse click + keyboard.type.

    chatgpt.com uses ProseMirror which (like Quill) needs real key events,
    not InputEvent. Same approach as gemini_web.
    """
    ok = await page.evaluate(
        """() => {
            const el = document.getElementById('prompt-textarea');
            if (el) {
                el.focus();
                return true;
            }
            const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
            const target = ces
                .map(e => ({e, w: e.offsetWidth, h: e.offsetHeight}))
                .filter(x => x.w > 50 && x.h > 0)
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
        raise RuntimeError("Could not find/focus ChatGPT prompt input")

    try:
        for sel in _PROMPT_SELECTORS:
            try:
                await page.locator(sel).first.click(timeout=3000)
                break
            except Exception:
                continue
    except Exception as exc:
        logger.warning("chatgpt_web: prompt mouse click failed: %s", str(exc)[:100])

    try:
        loc = page.locator('#prompt-textarea, [contenteditable=true]').first
        await loc.click(timeout=5000)
        await loc.clear()
        await loc.press_sequentially(prompt, delay=20)
        await asyncio.sleep(0.5)
        await page.keyboard.press("Enter")
        await asyncio.sleep(0.5)
    except Exception as e:
        logger.warning("chatgpt_web: press_sequentially failed: %s", e)
    await asyncio.sleep(0.5)

async def _click_send(page) -> bool:
    for sel in _SEND_SELECTORS:
        try:
            await page.locator(sel).first.click(timeout=1000)
            return True
        except:
            pass
        
        # JS fallback
        clicked = await page.evaluate(
            f"""() => {{
                const btn = document.querySelector('{sel}');
                if (btn) {{
                    btn.removeAttribute('disabled');
                    btn.click();
                    return true;
                }}
                return false;
            }}"""
        )
        if clicked:
            return True
    return False


async def _activate_tool(page, tool_name: str) -> bool:
    """Open '+' menu and click a tool by Vietnamese name.

    Tool names:
      'Tạo hình ảnh'   → DALL-E image generation
      'Tạo ảnh'        → alt label
      'Thêm ảnh và tệp'/'Tải tệp lên' → file upload trigger
      'Suy nghĩ đi'    → thinking mode
      'Tìm kiếm trên mạng' → web search
      'Nghiên cứu chuyên sâu' → deep research (paid)
    """
    plus_opened = False
    for sel in _PLUS_SELECTORS:
        try:
            await page.locator(sel).first.click(timeout=3000)
            logger.info("chatgpt_web: opened + menu via %s", sel)
            plus_opened = True
            break
        except Exception:
            continue
    if not plus_opened:
        logger.warning("chatgpt_web: no + button matched")
        return False

    # Wait for menu render (Radix or similar).
    for _ in range(20):
        await asyncio.sleep(0.2)
        visible = await page.evaluate(
            """() => {
                const m = document.querySelector('[role=menu], [data-radix-popper-content-wrapper]');
                return !!(m && m.offsetWidth > 0);
            }"""
        )
        if visible:
            break

    selectors = [
        f'[role=menu] [role=menuitem]:has-text("{tool_name}")',
        f'[role=menu] button:has-text("{tool_name}")',
        f'[data-radix-popper-content-wrapper] [role=menuitem]:has-text("{tool_name}")',
        f'[data-radix-popper-content-wrapper] button:has-text("{tool_name}")',
        f'button:has-text("{tool_name}")',
    ]
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=500)
            logger.info("chatgpt_web: activated tool '%s' via %s", tool_name, sel)
            await asyncio.sleep(0.8)
            return True
        except Exception:
            continue

    # JS fallback
    clicked = await page.evaluate(
        """(name) => {
            const t = name.toLowerCase();
            const items = Array.from(document.querySelectorAll(
                '[role=menu] [role=menuitem], [role=menu] button, '
                + '[data-radix-popper-content-wrapper] [role=menuitem], '
                + '[data-radix-popper-content-wrapper] button'
            ));
            for (const el of items) {
                if (el.offsetWidth === 0) continue;
                if ((el.innerText || '').toLowerCase().includes(t)) {
                    const r = el.getBoundingClientRect();
                    const opts = {bubbles:true, cancelable:true, clientX: r.left+r.width/2, clientY: r.top+r.height/2, button:0};
                    el.dispatchEvent(new PointerEvent('pointerdown', opts));
                    el.dispatchEvent(new MouseEvent('mousedown', opts));
                    el.dispatchEvent(new PointerEvent('pointerup', opts));
                    el.dispatchEvent(new MouseEvent('mouseup', opts));
                    el.click();
                    return (el.innerText || '').slice(0, 60);
                }
            }
            const visible = Array.from(document.querySelectorAll('[role=menu] *, [data-radix-popper-content-wrapper] *'))
                .filter(e => e.offsetWidth > 0)
                .map(e => (e.innerText || '').slice(0, 40).trim())
                .filter(t => t);
            return '__DEBUG__:' + JSON.stringify(visible.slice(0, 15));
        }""",
        tool_name,
    )
    if clicked and not clicked.startswith('__DEBUG__'):
        logger.info("chatgpt_web: activated '%s' via JS (%s)", tool_name, clicked)
        await asyncio.sleep(0.8)
        return True
    if clicked.startswith('__DEBUG__'):
        logger.warning("chatgpt_web: tool '%s' not found. Menu had: %s",
                        tool_name, clicked[len('__DEBUG__:'):])
    return False


async def _wait_for_response_complete(page, timeout: int = 90) -> str:
    """Wait for assistant response to finish streaming."""
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0
    while time.time() < deadline:
        await asyncio.sleep(1.0)
        text = await page.evaluate(
            """() => {
                const candidates = [
                    '[data-message-author-role="assistant"]',
                    'article:has([data-message-author-role="assistant"])',
                    '.markdown.prose',
                ];
                for (const sel of candidates) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) {
                        const last = nodes[nodes.length - 1];
                        const t = (last.innerText || '').trim();
                        if (t) return t;
                    }
                }
                return '';
            }"""
        )
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
    raise RuntimeError(f"ChatGPT didn't produce response within {timeout}s (last: {last_text!r})")


async def _wait_for_image(page, timeout: int = 180) -> list[str]:
    """Poll latest assistant response for <img> URLs."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(2.0)
        urls = await page.evaluate(
            """() => {
                const allImages = Array.from(document.querySelectorAll('img'));
                return allImages
                    .filter(img => {
                        const src = img.src || '';
                        if (src.includes('avatar') || src.includes('favicon')) return false;
                        return src.includes('oaiusercontent.com') || src.includes('chatgpt.com/backend-api/estuary/content') || src.startsWith('blob:');
                    })
                    .map(img => img.src)
                    .filter(src => src && (src.startsWith('http') || src.startsWith('data:image/') || src.startsWith('blob:')));
            }"""
        )
        if urls:
            return urls
    return []


async def list_models(profile: str, headless: bool = True, timeout: int = 30) -> list[dict[str, Any]]:
    """Fetch the live model catalogue from chatgpt.com.

    Uses the internal /backend-api/models endpoint (the same one the
    real chatgpt.com UI hits to populate the model picker). We `fetch`
    it from within an authenticated page so the session/edge cookies
    are attached automatically. Returns a list of normalized rows:
        [{"id": "cgw/gpt-5", "title": "GPT-5", "raw_slug": "..."}, ...]
    Empty list if the request fails (logged-out profile, Cloudflare,
    etc.) so /v1/models can fall back to the static catalogue without
    blowing up the whole models page.
    """
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=timeout * 1000)
        try:
            payload = await page.evaluate(
                """
                async () => {
                    const r = await fetch('/backend-api/models', { credentials: 'include' });
                    if (!r.ok) return { error: 'HTTP ' + r.status };
                    return await r.json();
                }
                """
            )
        except Exception as exc:
            logger.warning("chatgpt_web list_models fetch failed: %s", exc)
            return []
        if not isinstance(payload, dict) or "models" not in payload:
            logger.info("chatgpt_web list_models: unexpected payload %r", str(payload)[:200])
            return []
        out = []
        seen = set()
        for m in payload.get("models") or []:
            if not isinstance(m, dict):
                continue
            slug = str(m.get("slug") or "").strip()
            if not slug or slug in seen:
                continue
            seen.add(slug)
            out.append({
                "id": f"cgw/{slug}",
                "title": str(m.get("title") or slug),
                "raw_slug": slug,
                "description": str(m.get("description") or "")[:200],
            })
        return out


async def chat(profile: str, prompt: str, timeout: int = 90, headless: bool = False) -> dict[str, Any]:
    """Plain text chat with chatgpt.com (DOM-scrape).

    Returns text + per-stage timing (goto/ready/inject/send/response) so the
    Logs UI can pinpoint which stage made a slow call slow."""
    started = time.time()
    stages: dict[str, int] = {}
    async with pool.page(profile=profile, headless=headless) as page:
        t0 = time.time()
        await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=30_000)
        stages["goto_ms"] = int((time.time() - t0) * 1000); t1 = time.time()
        await _wait_for_ready(page, timeout=30)
        stages["ready_ms"] = int((time.time() - t1) * 1000); t2 = time.time()
        await _inject_prompt(page, prompt)
        stages["inject_ms"] = int((time.time() - t2) * 1000); t3 = time.time()
        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click ChatGPT Send button")
        
        text = await _wait_for_response_complete(page, timeout=timeout)
        stages["response_ms"] = int((time.time() - t3) * 1000)
        return {
            "text": text,
            "elapsed_ms": int((time.time() - started) * 1000),
            "stages": stages,
        }


async def generate_image(
    profile: str, prompt: str, timeout: int = 180, headless: bool = False,
) -> dict[str, Any]:
    """Generate image via DALL-E. Activates 'Tạo hình ảnh' tool first."""
    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_ready(page, timeout=30)

        activated = await _activate_tool(page, "Tạo hình ảnh")
        if not activated:
            activated = await _activate_tool(page, "Tạo ảnh")
        
        full_prompt = prompt
        if not activated:
            logger.warning("chatgpt_web: could not activate image tool, proceeding with natural language fallback")
            lower_prompt = prompt.lower()
            if not any(k in lower_prompt for k in ("vẽ", "tạo ảnh", "tạo hình ảnh", "generate an image", "draw", "create an image", "dall-e")):
                full_prompt = f"Vui lòng tạo hình ảnh (generate an image): {prompt}"

        await _inject_prompt(page, full_prompt)
        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Send")
        
        urls = await _wait_for_image(page, timeout=timeout)
        if not urls:
            try:
                import os
                os.makedirs("/data/debug", exist_ok=True)
                await page.screenshot(path="/data/debug/chatgpt_error.png")
                html = await page.content()
                with open("/data/debug/chatgpt_error.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info("chatgpt_web: saved debug screenshot and HTML to /data/debug/")
            except Exception as e:
                logger.warning("chatgpt_web: failed to take error debug info: %s", e)

            text = await page.evaluate(
                """() => {
                    const n = document.querySelectorAll('[data-message-author-role="assistant"]');
                    if (!n.length) return '';
                    return (n[n.length-1].innerText || '').slice(0, 300);
                }"""
            )
            raise RuntimeError(f"Không có ảnh sinh trong {timeout}s. ChatGPT: {text!r}")

        converted_urls = []
        for url in urls:
            if url.startswith("blob:") or "backend-api" in url:
                try:
                    data_uri = await page.evaluate(f"""async () => {{
                        const img = document.querySelector(`img[src="{url}"]`);
                        if (!img) throw new Error("Img element not found");
                        const canvas = document.createElement('canvas');
                        canvas.width = img.naturalWidth || img.width || 1024;
                        canvas.height = img.naturalHeight || img.height || 1024;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                        return canvas.toDataURL('image/jpeg', 0.95);
                    }}""")
                    converted_urls.append(data_uri)
                except Exception as e:
                    logger.warning("chatgpt_web: failed to convert blob URL: %s", e)
                    converted_urls.append(url)
            else:
                converted_urls.append(url)

        images = []
        for url in converted_urls:
            mime = url.split(";", 1)[0].replace("data:", "") if url.startswith("data:") else "image/png"
            images.append({"url": url, "mime": mime})
        return {
            "images": images,
            "count": len(images),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


async def analyze_image(
    profile: str, image: str, prompt: str = "Phân tích chi tiết nội dung ảnh này.",
    timeout: int = 120, headless: bool = False,
) -> dict[str, Any]:
    """Upload image + ask question via chatgpt.com (GPT vision)."""
    # Resolve image to temp file.
    if image.startswith("data:"):
        header, b64 = image.split(",", 1)
        mime = header.split(";")[0].replace("data:", "")
        data = base64.b64decode(b64)
    elif image.startswith(("http://", "https://")):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/130.0.0.0 Safari/537.36",
            "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
        }
        async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers=headers) as client:
            r = await client.get(image)
            r.raise_for_status()
        data = r.content
        mime = (r.headers.get("content-type") or "image/png").split(";")[0].strip()
    else:
        raise ValueError("image must be data: URL or http(s) URL")

    ext = mime.split("/")[1] if "/" in mime else "png"
    tmp = tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False)
    tmp.write(data)
    tmp.close()

    started = time.time()
    try:
        async with pool.page(profile=profile, headless=headless) as page:
            await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=30_000)
            await _wait_for_ready(page, timeout=30)

            # Upload via file_chooser intercepted by + → "Thêm ảnh và tệp"/'Tải tệp lên'.
            try:
                async with page.expect_file_chooser(timeout=15_000) as fc_info:
                    activated = await _activate_tool(page, "Thêm ảnh và tệp")
                    if not activated:
                        activated = await _activate_tool(page, "Tải tệp lên")
                    if not activated:
                        activated = await _activate_tool(page, "Tải lên")
                fc = await fc_info.value
                await fc.set_files(tmp.name)
                logger.info("chatgpt_web: uploaded %s (%s) via file chooser", tmp.name, mime)
            except Exception as exc:
                logger.warning("chatgpt_web: file_chooser failed (%s) — trying direct", str(exc)[:120])
                try:
                    await page.locator('input[type="file"]').first.set_input_files(tmp.name, timeout=5000)
                    logger.info("chatgpt_web: uploaded via input[type=file]")
                except Exception as exc2:
                    raise RuntimeError(f"Upload fail: chooser={exc} | input={exc2}") from exc2

            await asyncio.sleep(4.0)
            await _inject_prompt(page, prompt)
            sent = await _click_send(page)
            if not sent:
                raise RuntimeError("Could not click Send after upload")

            text = await _wait_for_response_complete(page, timeout=timeout)
            return {"text": text, "elapsed_ms": int((time.time() - started) * 1000)}
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass
