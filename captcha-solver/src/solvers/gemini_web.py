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
import json
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

    # Inject the prompt via native insertText command.
    # This is instant and triggers Quill's document listeners properly.
    injected = await page.evaluate(
        """(text) => {
            const ces = Array.from(document.querySelectorAll('[contenteditable=true]'));
            const target = ces
                .map(e => ({e, w: e.offsetWidth, h: e.offsetHeight}))
                .filter(x => x.w > 200 && x.h > 0)
                .sort((a, b) => (b.w * b.h) - (a.w * a.h))[0];
            if (!target) return false;
            target.e.focus();
            
            // Clear existing text first
            document.execCommand('selectAll', false, null);
            document.execCommand('delete', false, null);
            
            // Use execCommand to insert the entire text instantly
            return document.execCommand('insertText', false, text);
        }""",
        prompt,
    )
    if not injected:
        logger.warning("gemini_web: execCommand('insertText') failed, falling back to keyboard.type")
        await page.keyboard.type(prompt, delay=0)
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


async def _activate_tool(page, tool_name: str) -> bool:
    """Open the '+' (Thêm tệp) menu and click a tool by Vietnamese name.

    Gemini Free's image gen / music gen / canvas / deep research are
    NOT auto-detected from natural language — they're TOOLS that must
    be activated from the composer's + menu BEFORE typing the prompt.
    After activation a chip ('Hình ảnh' / 'Nhạc' / ...) appears below
    the input to confirm the mode.

    Tool names (case-insensitive substring match):
      'Tạo hình ảnh'   → image generation (Imagen)
      'Tạo nhạc'       → music generation (Lyria)
      'Canvas'         → canvas mode
      'Deep Research'  → deep research mode
      'Tải tệp lên'    → upload file (also works via input[type=file])
    """
    # 1. Open + menu via Playwright real mouse click.
    # Gemini renames this button across versions: 'Thêm tệp' (old) →
    # 'Nội dung tải lên và công cụ' (current 2026-05) → may change again.
    # Match by Vietnamese/English keywords in the aria-label.
    plus_selectors = [
        'button[aria-label*="Nội dung tải lên"]',
        'button[aria-label*="công cụ"]',
        'button[aria-label="Thêm tệp"]',
        'button[aria-label*="Add file"]',
        'button[aria-label*="Upload"]',
        'button[aria-label*="Attach"]',
        'button[aria-label*="Tools"]',
    ]
    plus_opened = False
    try:
        opened = await page.evaluate(
            """() => {
                const clean = (str) => (str || '').normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
                const btn = Array.from(document.querySelectorAll('button')).find(b => {
                    const al = clean(b.getAttribute('aria-label') || '');
                    return al.includes('tai len') || al.includes('cong cu') || al.includes('them tep') 
                        || al.includes('add file') || al.includes('upload') || al.includes('attach') 
                        || al.includes('tools') || al.includes('plus');
                });
                if (!btn) return false;
                btn.click();
                return true;
            }"""
        )
        if opened:
            logger.info("gemini_web: opened + menu via JS click")
            plus_opened = True
    except Exception as exc:
        logger.warning("gemini_web: plus menu JS click failed: %s", exc)

    if not plus_opened:
        for sel in plus_selectors:
            try:
                await page.locator(sel).first.click(timeout=3000)
                logger.info("gemini_web: opened + menu via %s", sel)
                plus_opened = True
                break
            except Exception as e:
                logger.warning("gemini_web: plus selector %s failed: %s", sel, str(e)[:150])
                continue
    if not plus_opened:
        labels = await page.evaluate(
            """() => {
                return Array.from(document.querySelectorAll('button'))
                    .map(b => `aria-label: "${b.getAttribute('aria-label') || ''}", text: "${(b.innerText || '').trim()}"`)
                    .filter(t => t);
            }"""
        )
        logger.warning("gemini_web: open + menu — no selector matched. Available buttons: %s", json.dumps(labels, ensure_ascii=False))
        return False

    # 2. Wait for Angular Material menu to render (cdk-overlay-pane).
    for _ in range(20):
        await asyncio.sleep(0.2)
        pane_visible = await page.evaluate(
            """() => {
                const pane = document.querySelector('.cdk-overlay-pane, [role=menu], mat-menu-content');
                return !!(pane && pane.offsetWidth > 0);
            }"""
        )
        if pane_visible:
            break

    # 3. Click menu item via Playwright (real click — JS .click() doesn't
    #    trigger the Angular Material item ripple/selection consistently).
    selectors = [
        f'.cdk-overlay-pane button:has-text("{tool_name}")',
        f'.cdk-overlay-pane [role=menuitem]:has-text("{tool_name}")',
        f'[role=menu] button:has-text("{tool_name}")',
        f'[role=menu] [role=menuitem]:has-text("{tool_name}")',
        f'mat-menu-content button:has-text("{tool_name}")',
        f'button:has-text("{tool_name}")',
    ]
    for sel in selectors:
        try:
            await page.locator(sel).first.click(timeout=2500)
            logger.info("gemini_web: activated tool '%s' via %s", tool_name, sel)
            await asyncio.sleep(0.8)
            return True
        except Exception:
            continue

    # 4. JS fallback with full mouse event sequence.
    clicked = await page.evaluate(
        """(name) => {
            const clean = (str) => (str || '').normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
            const t = clean(name);
            const items = Array.from(document.querySelectorAll(
                '.cdk-overlay-pane button, .cdk-overlay-pane [role=menuitem], '
                + '[role=menu] button, [role=menu] [role=menuitem], '
                + 'button[mat-menu-item], .mat-mdc-menu-item'
            ));
            for (const el of items) {
                if (el.offsetWidth === 0) continue;
                if (clean(el.innerText || '').includes(t)) {
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
            // Diagnostic: log all visible menu items so future failures know what's there.
            const visible = Array.from(document.querySelectorAll('.cdk-overlay-pane button, .cdk-overlay-pane [role=menuitem]'))
                .filter(e => e.offsetWidth > 0)
                .map(e => (e.innerText || '').slice(0, 40).trim())
                .filter(t => t);
            return '__DEBUG__:' + JSON.stringify(visible);
        }""",
        tool_name,
    )
    if clicked and not clicked.startswith('__DEBUG__'):
        logger.info("gemini_web: activated tool '%s' via JS fallback (%s)", tool_name, clicked)
        await asyncio.sleep(0.8)
        return True
    if clicked.startswith('__DEBUG__'):
        logger.warning("gemini_web: tool '%s' not found. Menu had: %s",
                        tool_name, clicked[len('__DEBUG__:'):])
    return False


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
                    '.model-response-text',
                    '.markdown',
                    '[data-test-id="response-content"]',
                    'model-response',
                    '.conversation-container .response',
                ];
                let lastResponse = null;
                for (const sel of candidates) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) { lastResponse = nodes[nodes.length - 1]; break; }
                }
                if (!lastResponse) return [];
                // Extract <img> URLs, filtering out tiny icons (< 100px).
                return Array.from(lastResponse.querySelectorAll('img'))
                    .filter(img => {
                        const src = img.src || '';
                        const isIcon = src.includes('google.com/maps') || src.includes('favicon') || img.closest('.avatar') || img.closest('user-avatar') || img.classList.contains('avatar') || img.className.includes('icon');
                        if (isIcon) return false;
                        return img.naturalWidth >= 100 || img.naturalHeight >= 100 || img.width >= 100 || src.includes('googleusercontent.com') || src.startsWith('data:image/');
                    })
                    .map(img => img.src)
                    .filter(src => src && (src.startsWith('http') || src.startsWith('data:image/') || src.startsWith('blob:')));
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
    """Generate image(s) via gemini.google.com (Imagen).

    Workflow (confirmed via real Gemini Web UI):
      1. Click + menu → activate 'Tạo hình ảnh' tool (badge appears)
      2. Type prompt → Send
      3. Wait for <img> tags in the response container

    Without step 1 Gemini just chats back the description — doesn't
    actually generate. count parameter is appended to the prompt as
    a hint to Imagen.

    Returns:
        {"images": [{"url", "mime"}, ...], "count": int, "elapsed_ms": int}
    """
    full_prompt = f"{prompt} ({count} ảnh)" if count > 1 else prompt

    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_ready(page, timeout=30)

        # 1. Activate the image tool from the + menu.
        activated = await _activate_tool(page, "Tạo hình ảnh")
        if not activated:
            raise RuntimeError(
                "Không bật được tool 'Tạo hình ảnh' (account có thể chưa có Imagen)"
            )

        # 2. Type prompt + send.
        await _inject_prompt(page, full_prompt)
        await asyncio.sleep(0.4)
        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Gemini Send button")

        urls = await _wait_for_image(page, timeout=timeout)
        if not urls:
            try:
                import os
                os.makedirs("/data/debug", exist_ok=True)
                await page.screenshot(path="/data/debug/gemini_error.png")
                html = await page.content()
                with open("/data/debug/gemini_error.html", "w", encoding="utf-8") as f:
                    f.write(html)
                logger.info("gemini_web: saved debug screenshot and HTML to /data/debug/")
            except Exception as e:
                logger.warning("gemini_web: failed to take error debug info: %s", e)

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

        converted_urls = []
        for url in urls:
            if url.startswith("blob:"):
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
                    logger.warning("gemini_web: failed to convert blob URL: %s", e)
                    converted_urls.append(url)
            else:
                converted_urls.append(url)
        
        # Detect mime from URL prefix.
        images = []
        for url in converted_urls:
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


async def analyze_image(
    profile: str,
    image: str,
    prompt: str = "Phân tích nội dung ảnh này một cách chi tiết.",
    timeout: int = 120,
    headless: bool = False,
) -> dict[str, Any]:
    """Upload an image to gemini.google.com and ask a question about it.

    Args:
        image: either a `data:image/<mime>;base64,<...>` data URL or an
               https URL to an image. The captcha-solver downloads it
               and uploads it to Gemini.
        prompt: text question to ask alongside the image.

    Returns:
        {"text": <Gemini's analysis>, "elapsed_ms": int}
    """
    import base64
    import os
    import tempfile

    import httpx

    # 1. Resolve image → temp file on disk (Playwright set_input_files
    #    requires a real path).
    if image.startswith("data:"):
        header, b64 = image.split(",", 1)
        mime = header.split(";")[0].replace("data:", "")
        data = base64.b64decode(b64)
    elif image.startswith(("http://", "https://")):
        # Some CDNs (Wikipedia, etc) reject default httpx UA — send a
        # browser-like UA so downloads don't 403.
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
            await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
            await _wait_for_ready(page, timeout=30)

            # 2. Gemini's file input is created LAZILY by the + menu's
            #    'Tải tệp lên' / 'Thêm ảnh và tệp' items — it doesn't
            #    exist in the DOM at page load. We use Playwright's
            #    expect_file_chooser to intercept the native file dialog
            #    that opens when we click the menu item, then upload via
            #    that chooser (works even when the underlying <input>
            #    never makes it into the visible DOM).
            try:
                async with page.expect_file_chooser(timeout=15_000) as fc_info:
                    activated = await _activate_tool(page, "Tải tệp lên")
                    if not activated:
                        # Some Gemini builds label it 'Thêm ảnh và tệp'.
                        activated = await _activate_tool(page, "Thêm ảnh")
                file_chooser = await fc_info.value
                await file_chooser.set_files(tmp.name)
                logger.info("gemini_web: uploaded image %s (mime=%s) via file chooser",
                            tmp.name, mime)
            except Exception as exc:
                # Fall back: maybe the input IS in the DOM after we open
                # the + menu. Try direct set_input_files.
                logger.warning("gemini_web: file_chooser flow failed (%s) — trying direct input", str(exc)[:120])
                try:
                    await page.locator('input[type="file"]').first.set_input_files(tmp.name, timeout=5000)
                    logger.info("gemini_web: uploaded image %s via input[type=file]", tmp.name)
                except Exception as exc2:
                    raise RuntimeError(
                        f"Không upload được ảnh: chooser={exc} | input={exc2}"
                    ) from exc2

            # 3. Wait for thumbnail / preview to appear.
            await asyncio.sleep(4.0)

            # 4. Type prompt + send.
            await _inject_prompt(page, prompt)
            await asyncio.sleep(0.4)
            sent = await _click_send(page)
            if not sent:
                raise RuntimeError("Không click được nút Send sau khi upload")

            # 5. Wait for response (longer timeout — vision often takes 20-40s).
            text = await _wait_for_response_complete(page, timeout=timeout)
            return {
                "text": text,
                "elapsed_ms": int((time.time() - started) * 1000),
            }
    finally:
        try:
            os.unlink(tmp.name)
        except Exception:
            pass


async def _wait_for_audio(page, timeout: int = 180) -> list[str]:
    """Poll the latest response container for <audio> / <video> tags with
    source URLs. Music gen typically takes 30-90s."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        await asyncio.sleep(3.0)
        urls = await page.evaluate(
            """() => {
                const candidates = [
                    'message-content', 'model-response', '.model-response-text',
                ];
                let lastResponse = null;
                for (const sel of candidates) {
                    const nodes = document.querySelectorAll(sel);
                    if (nodes.length > 0) { lastResponse = nodes[nodes.length - 1]; break; }
                }
                if (!lastResponse) return [];
                const out = [];
                // <audio> with src or <source>
                lastResponse.querySelectorAll('audio').forEach(a => {
                    if (a.src) out.push(a.src);
                    a.querySelectorAll('source').forEach(s => { if (s.src) out.push(s.src); });
                });
                // <video> too (Lyria sometimes wraps audio in video player)
                lastResponse.querySelectorAll('video').forEach(v => {
                    if (v.src) out.push(v.src);
                    v.querySelectorAll('source').forEach(s => { if (s.src) out.push(s.src); });
                });
                // Or download links pointing at audio
                lastResponse.querySelectorAll('a[href*=".mp3"], a[href*=".wav"], a[href*=".ogg"], a[href*=".m4a"], a[href*="audio"]').forEach(a => {
                    if (a.href) out.push(a.href);
                });
                return out.filter(u => u && (u.startsWith('http') || u.startsWith('data:audio') || u.startsWith('blob:')));
            }"""
        )
        if urls and len(urls) > 0:
            return urls
    return []


async def generate_music(
    profile: str,
    prompt: str,
    timeout: int = 180,
    headless: bool = False,
) -> dict[str, Any]:
    """Generate music via gemini.google.com (Lyria).

    Workflow same as image gen but activates 'Tạo nhạc' tool.

    Returns:
        {"audio": [{"url", "mime"}, ...], "elapsed_ms": int}
    """
    started = time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        await _wait_for_ready(page, timeout=30)

        activated = await _activate_tool(page, "Tạo nhạc")
        if not activated:
            raise RuntimeError(
                "Không bật được tool 'Tạo nhạc' (account có thể chưa có Lyria)"
            )

        await _inject_prompt(page, prompt)
        await asyncio.sleep(0.4)
        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Gemini Send button")

        urls = await _wait_for_audio(page, timeout=timeout)
        if not urls:
            text = await page.evaluate(
                """() => {
                    const n = document.querySelectorAll('message-content');
                    if (!n.length) return '';
                    return (n[n.length-1].innerText || '').slice(0, 300);
                }"""
            )
            raise RuntimeError(
                f"Không có nhạc sinh trong {timeout}s. Gemini có thể từ chối: {text!r}"
            )

        audio = []
        for url in urls:
            if url.startswith("data:audio/"):
                mime = url.split(";", 1)[0].replace("data:", "")
            elif url.endswith(".wav"):
                mime = "audio/wav"
            elif url.endswith(".ogg"):
                mime = "audio/ogg"
            elif url.endswith(".m4a"):
                mime = "audio/mp4"
            else:
                mime = "audio/mpeg"
            audio.append({"url": url, "mime": mime})

        return {
            "audio": audio,
            "count": len(audio),
            "elapsed_ms": int((time.time() - started) * 1000),
        }


async def list_models(profile: str, headless: bool = True, timeout: int = 30) -> list[dict[str, Any]]:
    """Scrape the model picker on gemini.google.com.

    Gemini Web has no public "list models" API. The picker is rendered
    inside a Material-style menu — we open the menu, read the rendered
    button labels, then close it. Returns rows like
        [{"id": "gmw/gemini-2.5-pro", "title": "2.5 Pro"}, ...]
    with the prefix normalized to `gmw/`. Empty list on any error
    (logged-out profile, picker missing, layout change) so /v1/models
    can fall back to the static catalogue without erroring out.
    """
    import re

    def _slug(label: str) -> str:
        s = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
        return s or "unknown"

    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=timeout * 1000)
        try:
            await _wait_for_ready(page, timeout=15)
        except Exception:
            pass

        # Scrape with JS instead of Playwright locators — Google's Angular
        # build rotates role attributes (`menuitemradio` / `menuitem` /
        # nothing at all) often enough that selector-only approaches are
        # fragile. We rely on the picker labels following a stable text
        # pattern ("2.5 Pro", "3.1 Flash", "Deep Think", "Imagen") and
        # filter by visibility so we don't pick up off-screen content.
        scraped = await page.evaluate(
            """
            async () => {
                const sleep = ms => new Promise(r => setTimeout(r, ms));
                // Find the picker button. Try stable attrs first, fall
                // back to any button whose label looks model-like.
                const allButtons = Array.from(document.querySelectorAll('button'));
                const stable = allButtons.find(b =>
                    b.getAttribute('data-test-id') === 'bard-mode-menu-button'
                );
                const fuzzy = allButtons.find(b => {
                    const t = (b.innerText || b.getAttribute('aria-label') || '').trim();
                    return /\\b(model|2\\.5|3\\.|3\\b|flash|pro|deep think|imagen)\\b/i.test(t)
                        && b.offsetParent !== null;
                });
                const picker = stable || fuzzy;
                if (!picker) return { error: 'picker_not_found', sample: allButtons.slice(0, 5).map(b => (b.innerText || '').slice(0, 40)) };
                picker.click();
                await sleep(1500);
                // After the picker opens, harvest visible text that matches
                // the model-name pattern. Use a Set to dedupe across nested
                // wrappers that often repeat the same label.
                const visible = el => {
                    const r = el.getBoundingClientRect();
                    return r.width > 0 && r.height > 0;
                };
                const out = new Set();
                for (const el of document.querySelectorAll('*')) {
                    if (!visible(el)) continue;
                    if (el.children.length > 3) continue;  // skip wrapper nodes
                    const text = (el.innerText || '').trim();
                    if (text.length < 2 || text.length > 60) continue;
                    // Match the model-name patterns the picker uses:
                    //   chat tiers: 2.5/3.1/3 + Flash/Pro/Deep Think/Thinking
                    //   image gens: Imagen N, Nano Banana (Pro / N)
                    if (/^(?:\\d+\\.?\\d*\\s+)?(?:Flash(?:-Lite| Extended)?|Pro(?: Thinking| with Deep Think)?|Deep Think|Imagen \\d+|Nano Banana(?: \\d+| Pro)?)\\b/i.test(text)) {
                        out.add(text);
                    }
                }
                // Close the picker before returning.
                document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
                return { models: Array.from(out) };
            }
            """
        )
        labels: list[str] = []
        if isinstance(scraped, dict):
            if scraped.get("error"):
                logger.info("gemini_web list_models: %s sample=%r",
                            scraped["error"], scraped.get("sample"))
            for m in (scraped.get("models") or []):
                cleaned = " ".join(str(m).split())
                if cleaned and 2 <= len(cleaned) < 60:
                    labels.append(cleaned)

    # Augment picker output with everything the passive tracker has
    # observed in past RPC responses (image / music / video tools never
    # appear in the dropdown, but their model names show up in the
    # wrb.fr footer the first time the user actually invokes them).
    try:
        from .model_tracker import list_seen as _list_seen
        for tracked in _list_seen("gemini_web", profile):
            labels.append(tracked)
    except Exception:
        pass

    # Gemini's picker renders each tier twice: once as the bare model
    # name (e.g. "3.1 Flash-Lite") and once as name + tagline ("3.1
    # Flash-Lite Câu trả lời nhanh nhất"). Keep the short form. Match
    # is on the first 1-3 tokens of model-shaped text.
    import re as _re
    short_pattern = _re.compile(
        r"^("
        r"(?:\d+(?:\.\d+)?\s+)?(?:Flash(?:-Lite| Extended)?|Pro(?: Thinking)?|Deep Think)"
        r"|Imagen\s+\d+"
        r"|Nano Banana(?:\s+\d+| Pro)?"
        r"|Lyria"
        r")",
        _re.IGNORECASE,
    )
    out = []
    seen_titles = set()
    seen_slugs = set()
    for raw_label in labels:
        # Strip secondary descriptor on newline.
        candidate = raw_label.split("\n")[0].strip() if "\n" in raw_label else raw_label
        m = short_pattern.match(candidate)
        title = m.group(1).strip() if m else candidate.strip()
        if not title:
            continue
        # Canonicalize whitespace so "3.1  Flash" and "3.1 Flash" dedupe.
        canonical = " ".join(title.split()).lower()
        if canonical in seen_titles:
            continue
        seen_titles.add(canonical)
        slug = _slug(title)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        out.append({
            "id": f"gmw/{slug}",
            "title": title,
            "raw_slug": slug,
        })
    return out


async def get_plan(profile: str, headless: bool = True, timeout: int = 30) -> dict[str, Any]:
    """Detect the Gemini Web subscription tier for `profile`.

    No public API for this — gemini.google.com encodes the plan in the
    page header / left rail ("Gemini", "Gemini Advanced", "Gemini AI
    Pro", "Gemini Ultra"). Open the app, harvest visible text,
    classify with a vocabulary regex. Returns
        {"plan": "free|plus|pro|ultra", "label": "<raw label>"}
    Plan="free" is the fallback when nothing premium-shaped is on
    the page.
    """
    import re
    async with pool.page(profile=profile, headless=headless) as page:
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=timeout * 1000)
        try:
            await _wait_for_ready(page, timeout=15)
        except Exception:
            pass
        await asyncio.sleep(1.5)
        # The plan label is in the header area — collect everything
        # visible in the top-left brand region and the user account
        # menu. Inner_text on the whole body is cheap and reliable.
        body_text = ""
        try:
            body_text = (await page.locator("body").inner_text(timeout=2000)) or ""
        except Exception:
            pass
    raw = body_text or ""
    raw_lower = raw.lower()
    # Order matters — match the most specific tier first.
    if re.search(r"\bgemini\s+ultra\b", raw_lower):
        return {"plan": "ultra", "label": "Gemini Ultra"}
    if re.search(r"\bgemini\s+ai\s+pro\b", raw_lower) or re.search(r"\bgemini\s+pro\b", raw_lower):
        return {"plan": "pro", "label": "Gemini AI Pro"}
    if re.search(r"\bgemini\s+advanced\b", raw_lower) or re.search(r"\bgemini\s+plus\b", raw_lower):
        return {"plan": "plus", "label": "Gemini Advanced"}
    return {"plan": "free", "label": "Gemini"}


async def chat(profile: str, prompt: str, timeout: int = 90, headless: bool = False) -> dict[str, Any]:
    """Send a single prompt to gemini.google.com and return its response.

    Returns:
        {
          "text": <assistant response>,
          "elapsed_ms": int,
          "stages": {goto, ready, inject, send, response} — per-stage ms,
        }

    Profile must already be logged in via gemini_web_login.
    Each call opens a fresh chat (no history) — for multi-turn, the
    caller passes the previous messages in `prompt` as serialized text.

    The `stages` map is what makes the slow-call diagnosis possible —
    if elapsed_ms is high we want to know whether it was the
    page open (cold profile, network), waiting for the chat UI to
    hydrate (auth flicker, server-side delay), or actually waiting on
    Gemini to finish streaming (long prompts, big tools).
    """
    started = time.time()
    stages: dict[str, int] = {}
    def _mark(name: str, since: float) -> float:
        stages[name] = int((time.time() - since) * 1000)
        return time.time()
    async with pool.page(profile=profile, headless=headless) as page:
        t0 = time.time()
        await page.goto(_GEMINI_HOME, wait_until="domcontentloaded", timeout=30_000)
        t1 = _mark("goto_ms", t0)
        await _wait_for_ready(page, timeout=30)
        t2 = _mark("ready_ms", t1)

        await _inject_prompt(page, prompt)
        await asyncio.sleep(0.4)
        t3 = _mark("inject_ms", t2)

        sent = await _click_send(page)
        if not sent:
            raise RuntimeError("Could not click Gemini Send button")
        t4 = _mark("send_ms", t3)

        text = await _wait_for_response_complete(page, timeout=timeout)
        _mark("response_ms", t4)
        return {
            "text": text,
            "elapsed_ms": int((time.time() - started) * 1000),
            "stages": stages,
        }
