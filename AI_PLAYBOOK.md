# AI Assistant Playbook — chatgpt2api / captcha-solver

> Mục đích: ghi lại cách suy nghĩ + các pattern giải quyết đã hiệu quả với codebase này, để bất kỳ AI assistant nào (Claude, ChatGPT, Gemini, ...) tiếp quản đều có sẵn lối tiếp cận thay vì học lại từ đầu.

---

## 1. Triết lý debug (quan trọng nhất)

Khi user báo bug, luôn theo thứ tự:

1. **Reproduce** bằng cách gọi đúng endpoint đó qua `curl` với body từ file `@/d/Chatgpt/_test_*.json` (tránh shell escape mangling Unicode).
2. **Đọc log container** `docker logs <name> --tail N 2>&1 | grep -iE "(pattern)"` — KHÔNG GUESS trước khi xem log.
3. **Probe DOM/state thực tế** bằng `POST /v1/browser/run` với JS evaluate, không tin tài liệu / screenshot cũ.
4. **Identify root cause** rồi mới sửa. Mỗi commit message giải thích **vì sao**, không chỉ **làm gì**.
5. **Verify E2E** sau khi deploy. Đừng đánh dấu done dựa trên build pass.

**Anti-pattern**: thấy lỗi → đoán fix → deploy → retest. Tốn thời gian gấp 3-5 lần so với probe trước.

---

## 2. Pattern xử lý web scraping (Patchright + Playwright)

Các loại editor có quy tắc khác nhau — chọn đúng method nếu không sẽ kẹt vô tận:

| Editor | Trang dùng | Cách inject text | Cách click submit |
|---|---|---|---|
| **Slate.js** | Google Labs Flow, một số app React | `InputEvent('beforeinput', {inputType:'insertText',data:text})` qua page.evaluate. **`keyboard.type` KHÔNG sync vào React state** | JS click + full PointerEvent + MouseEvent dispatch sequence |
| **Quill (ql-editor)** | Gemini Web | `page.locator.click()` real mouse → `page.keyboard.type()` real keys. **`InputEvent` KHÔNG fire Quill handlers** | `page.locator.click()` |
| **ProseMirror** | chatgpt.com | Giống Quill (real click + keyboard.type) | `data-testid="send-button"` selector trước, JS dispatch fallback |
| `<textarea>` / `<input>` thường | API forms | `await el.fill(text)` | Bình thường |

### Click bị overlay chặn?

```python
# 1. Thử Playwright locator.click() — real mouse, bypass nhiều intercept
await page.locator('button:has-text("Submit")').first.click(timeout=5000)

# 2. Nếu Timeout — remove overlay trước (chỉ overlay layer, KHÔNG remove dialog content)
await page.evaluate("""
    () => {
        document.querySelectorAll('[data-state="open"]').forEach(el => {
            if (el.getAttribute('role')) return;  // keep dialog content
            const r = el.getBoundingClientRect();
            if (r.width >= window.innerWidth * 0.8 && r.height >= window.innerHeight * 0.8) {
                el.remove();
            }
        });
    }
""")

# 3. Cuối cùng: JS dispatch full mouse sequence (React event delegation cần đủ chuỗi)
await page.evaluate("""
    (sel) => {
        const btn = document.querySelector(sel);
        const r = btn.getBoundingClientRect();
        const opts = {bubbles:true, cancelable:true, clientX: r.left+r.width/2, clientY: r.top+r.height/2, button:0};
        btn.dispatchEvent(new PointerEvent('pointerdown', opts));
        btn.dispatchEvent(new MouseEvent('mousedown', opts));
        btn.dispatchEvent(new PointerEvent('pointerup', opts));
        btn.dispatchEvent(new MouseEvent('mouseup', opts));
        btn.click();
    }
""", selector)
```

### File upload cho web AI (Gemini, ChatGPT)

Hidden `<input type="file">` lazy — chỉ tồn tại sau khi user click menu item. Dùng `expect_file_chooser`:

```python
async with page.expect_file_chooser(timeout=15_000) as fc_info:
    await _activate_tool(page, "Tải tệp lên")  # click menu trigger
file_chooser = await fc_info.value
await file_chooser.set_files(tmp_path)
```

### Tool activation pattern (Gemini + ChatGPT + Flow đều giống)

Modern AI web UI có `+` menu chứa các tool (image gen, music gen, file upload, search, ...). Activate đúng cách:

```python
# 1. Click + button — aria-label thường đổi giữa các version
for sel in ['button[aria-label*="Nội dung tải lên"]',  # Gemini 2026-05
            'button[aria-label="Thêm tệp"]',              # Gemini old
            'button[data-testid="composer-plus-btn"]',    # ChatGPT
            'button[aria-label*="Add"]']:
    try:
        await page.locator(sel).first.click(timeout=3000)
        break
    except Exception: continue

# 2. Wait CDK overlay render (Angular Material lazy)
for _ in range(20):
    await asyncio.sleep(0.2)
    if await page.evaluate("() => !!document.querySelector('.cdk-overlay-pane[style*=\"width\"]')"):
        break

# 3. Click menu item by text (multi-selector fallback)
for sel in [f'.cdk-overlay-pane button:has-text("{name}")',
            f'[role=menu] [role=menuitem]:has-text("{name}")',
            f'button:has-text("{name}")']:
    try:
        await page.locator(sel).first.click(timeout=2500)
        return True
    except Exception: continue

# 4. Last resort: JS evaluate match by innerText + dispatch full mouse sequence
```

### Detect response stable (streaming)

Async LLM trả lời từng token. Đừng return ngay khi thấy text — đợi 2 polls liên tiếp text giống nhau:

```python
async def wait_for_response(page, timeout=90):
    deadline = time.time() + timeout
    last_text = ""
    stable_count = 0
    while time.time() < deadline:
        await asyncio.sleep(1.0)
        text = await page.evaluate("...selector_for_last_response...")
        if _is_placeholder(text): continue  # skip "Đang tạo...", "generating..."
        if text == last_text:
            stable_count += 1
            if stable_count >= 2: return text
        else:
            stable_count = 0
            last_text = text
    raise RuntimeError(f"timeout (last: {last_text!r})")

_PLACEHOLDERS = ("đang tạo", "đang suy nghĩ", "generating", "thinking", "creating", "gemini đã nói")
def _is_placeholder(text):
    if not text: return True
    t = text.lower().strip()
    return len(t) < 60 and any(p in t for p in _PLACEHOLDERS)
```

---

## 3. Architecture / Provider patterns

### Cấu trúc 2 service chính

- **chatgpt2api** (port 3030): FastAPI + Next.js UI. OpenAI-compat `/v1/chat/completions`, `/v1/images/generations`. Routes via `BackendRouter` → multiple providers (Codex/OpenAI/Gemini/Flow/etc).
- **captcha-solver** (port 8010 + 6080 noVNC): FastAPI + Patchright headful Chrome trong Xvfb. Mỗi profile = persistent `user-data-dir` cho 1 account. Endpoints `/v1/session/manual-login`, `/v1/chatgpt/onboard`, `/v1/gemini-web/{chat,generate-image,analyze-image,generate-music}`, `/v1/chatgpt-web/{chat,generate-image,analyze-image}`.

### BackendRouter prefix convention

Add provider mới = 4 chỗ:

```python
# 1. services/backend_router.py
PROVIDER_PREFIXES["abc/"] = "abc_provider"

# 2. services/protocol/openai_v1_chat_complete.py _dispatch()
elif route.provider == "abc_provider":
    from services.providers.abc import handle_chat
    return handle_chat(route.model, messages, body.get("stream"), body)

# 3. services/providers/abc.py — handler returns OpenAI-format chat.completion
# 4. (optional) UI card in web/src/app/settings/components/abc-card.tsx
```

### Vision auto-detect pattern (web providers)

Cùng provider có thể serve text + vision + image-gen qua 1 model prefix bằng cách auto-detect content block. Áp dụng ở [services/providers/web_proxy.py](services/providers/web_proxy.py) (gmw/, cgw/):

```python
def _last_user_image(messages: list[dict[str, Any]]) -> str | None:
    """Reverse-scan user messages for an image_url / input_image part."""
    for m in reversed(messages):
        if m.get("role") != "user": continue
        content = m.get("content")
        if not isinstance(content, list): continue
        for p in reversed(content):
            if not isinstance(p, dict): continue
            if p.get("type") == "image_url":
                iu = p.get("image_url")
                url = iu.get("url") if isinstance(iu, dict) else iu
                if isinstance(url, str): return url
            elif p.get("type") == "input_image":
                url = p.get("image_url") or p.get("url")
                if isinstance(url, str): return url
    return None

def handle_chatgpt_web_chat(model, messages, stream, body):
    image_url = _last_user_image(messages)
    prompt = _last_user_text(messages)
    if image_url:
        if not prompt: prompt = "Phân tích chi tiết nội dung ảnh này."
        text = _call_web_vision("chatgpt-web", profile, image_url, prompt, ...)
        full_model = "cgw/vision"
    else:
        text = _call_web_chat("chatgpt-web", profile, prompt, ...)
        full_model = f"cgw/{model.split('/', 1)[-1]}"
    return _build_openai_response(text, full_model)  # or _stream_chunks
```

Cho `/v1/images/generations` riêng: trong [services/protocol/openai_v1_image_generations.py](services/protocol/openai_v1_image_generations.py) `_handle_single_image()` check `route.provider in ("gemini_web", "chatgpt_web")` rồi `from services.providers.web_proxy import handle_*_image_gen`.

### OAuth pattern cho web account (ChatGPT free)

Playwright login → scrape `/api/auth/session` → JWT có audience riêng:

```python
async def _scrape_session(page):
    result = await page.evaluate(
        """async (url) => {
            const r = await fetch(url, { credentials: 'include' });
            const text = await r.text();
            try { return {status: r.status, json: JSON.parse(text)}; }
            catch { return {status: r.status, text: text.slice(0,500)}; }
        }""",
        "https://chatgpt.com/api/auth/session",
    )
    return result.get("json") if result.get("status") == 200 else None
```

JWT có `chatgpt_plan_type: "free"` → bypass session-token 24KB limit, dùng được với `chatgpt.com/backend-api` trực tiếp.

### Strict-priority account rotation (Flow pattern, dùng cho mọi pool)

Không round-robin (load balance) — priority FIFO (Main → Backup → Spare 1 → 2 → ...). Auto-reset sau cooldown:

```python
def _next_account(exclude=None):
    accounts = _accounts()  # config order = priority order
    exclude = exclude or set()
    now = time.time()
    for idx in range(len(accounts)):  # ALWAYS iterate from 0
        acc = accounts[idx]
        key = _account_key(acc)
        if key in exclude: continue
        cooldown_until = _account_state.get(key, {}).get("cooldown_until", 0)
        if cooldown_until and now < cooldown_until: continue
        return acc
    return None  # pool exhausted
```

### BrowserPool — must do

- **Track mode per cached entry**: `_PoolEntry(ctx, headless)` — context headless không serve được headful request và ngược lại.
- **Liveness probe trước reuse**: `await asyncio.wait_for(ctx.cookies(), timeout=2.5)` — context chết khi user đóng Chrome qua noVNC.
- **Clear SingletonLock trước launch**: `/data/profiles/<name>/{SingletonLock, SingletonSocket, SingletonCookie}` còn lại sau crash sẽ chặn Chrome mới.
- **Subscribe close handler**: `context.on("close", ...)` để auto-drop cache.

---

## 4. Lessons learned (sai lầm + workaround)

### Volume mount phải khớp container's hardcoded path

```bash
# WRONG: code uses CAPTCHA_SOLVER_DATA_DIR=/data nhưng mount sai
docker run -v /opt/data:/app/data ...   # → profile lưu vào /data (ephemeral!) → mất sau redeploy

# RIGHT: mount đúng path code đọc
docker run -v /opt/data:/data ...
```

Symptom: profile size 167MB → 44MB sau redeploy = mất session. Check `settings.data_dir` vs mount path.

### Conservative threshold giết UX

`FREE_PAYLOAD_LIMIT = 24_000` (chatgpt2api) làm router redirect khỏi ChatGPT free + RTK truncate system prompt 26.7KB của HA → AI hallucinate tên entity. Raise 80KB → fix cả 2 issue. Raise tiếp 100KB (2026-05-25) — sát hard-limit chatgpt.com backend; payload vượt mức vẫn được RTK compress trước khi gửi. **Luôn benchmark giới hạn thực tế trước khi đặt conservative cap.**

### gpt-4o → Codex = 400

HA `ai_task` entity + nhiều OpenAI SDK clients hard-code `model=gpt-4o`. Codex chỉ accept `gpt-5.x-codex` family. Map ở dispatcher:

```python
_UNSUPPORTED = ("gpt-3.5", "gpt-4o", "gpt-4-", "gpt-4.", "gpt-5o", "gpt-5-")
if any(model.startswith(p) for p in _UNSUPPORTED):
    model = "auto"  # Codex tự pick từ enabled list
```

### Gemini API VN block

`generativelanguage.googleapis.com` chặn IP Việt Nam → 4/5 keys báo `error_400 "User location is not supported"`. Workaround:
- 1 key may still work (try rotation)
- Switch to **Gemini Web** scraping (gemini.google.com — không bị geo-block)
- Proxy US (Cloudflare Worker free, Squid trên VPS US, ...)

### Image download UA spoofing

Wikipedia / nhiều CDN từ chối default `httpx` UA → 403:

```python
async with httpx.AsyncClient(timeout=30, follow_redirects=True, headers={
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/130.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/png,image/*,*/*;q=0.8",
}) as client:
    r = await client.get(image_url)
```

### Free tier quota

- ChatGPT Free DALL-E: ~3 ảnh/ngày
- Gemini Free Imagen: có quota / region-restricted
- Gemini Free Lyria (music): chỉ có ở 1 số region/account

Detect via response: nếu "Đang tạo..." không chuyển thành actual content sau 150s+ → likely quota.

### Vision trên ChatGPT free path (fixed 2026-05-25)

Trước: gửi multimodal block `image_url` đến `chatgpt/free/auto` → AI trả "Bạn chưa gửi ảnh". Đường chatgpt provider đi qua [services/openai_backend_api.py](services/openai_backend_api.py) `_api_messages_to_conversation_messages()` — code có sẵn `_upload_image()` + `asset_pointer` qua `/backend-api/files` (estuary) **nhưng chỉ accept `part_type == "image"` với bytes data**, không hiểu OpenAI standard `image_url`/`input_image` blocks. Output rỗng image → backend trả lời như không có ảnh.

Fix: `_api_messages_to_conversation_messages` giờ nhận thêm `image_url`/`input_image`, tự decode `data:...;base64,...` hoặc download HTTP URL (UA spoof) → bytes → đẩy qua `_upload_image` flow có sẵn → `multimodal_text` part với `asset_pointer`. Pattern giống `services/protocol/openai_v1_chat_complete.py::_convert_images_for_openai` (codex path).

Note `message_text()` ở [services/protocol/conversation.py:170](services/protocol/conversation.py#L170) vẫn chỉ trả text — nhưng nó chỉ dùng cho compress / search-injection logic, không phải payload chính lên chatgpt.com:

```python
def message_text(content: Any) -> str:
    if isinstance(content, str): return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and str(item.get("type") or "") in {"text","input_text","output_text"}:
                parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return ""
```

`chatgpt.com/backend-api` không nhận inline base64 — phải upload qua estuary endpoint trước rồi attach `asset_pointer`. Code không implement bước này.

Cả free + codex JWT đều dùng được `/backend-api/files` (đã verified). Fallback ở [services/protocol/openai_v1_chat_complete.py](services/protocol/openai_v1_chat_complete.py) `_dispatch` vẫn còn — chỉ trigger khi không có ANY active chatgpt account (anon pool) → redirect `gemini_free`.

### JWT free 28-day expiry — auto-refresh pattern

JWT của ChatGPT free hết hạn sau ~28 ngày. Browser profile có cookie persist → re-scrape `/api/auth/session` lấy token mới mà không cần login Google.

Endpoint mới ở captcha-solver: [captcha-solver/src/main.py](captcha-solver/src/main.py) `POST /v1/chatgpt/{profile}/refresh-jwt`. Code: [captcha-solver/src/chatgpt_login.py](captcha-solver/src/chatgpt_login.py) `refresh_jwt(profile, timeout=30)`:

```python
async def refresh_jwt(profile: str, timeout: int = 30) -> dict:
    """Open profile (no login flow), goto chatgpt.com, scrape session."""
    ctx = await pool.get(profile=profile, headless=True, force_recreate=False)
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    await page.goto(_CHATGPT_HOME, wait_until="domcontentloaded", timeout=timeout*1000)
    await asyncio.sleep(1.5)
    scraped = await _scrape_session(page)
    if not scraped or not scraped.get("accessToken"):
        raise RuntimeError("Profile not logged in or session expired")  # → HTTP 401
    return {"access_token": scraped["accessToken"],
            "expires": str(scraped.get("expires") or ""),
            "email": (scraped.get("user") or {}).get("email")}
```

Scheduler chatgpt2api: [services/jwt_refresh_scheduler.py](services/jwt_refresh_scheduler.py) (started in `api/app.py` lifespan). Quy tắc:
- Quét mỗi `SCAN_INTERVAL_SECONDS` (6h)
- Decode JWT payload (base64url middle segment) — không verify signature
- Refresh khi `(exp - now) <= REFRESH_THRESHOLD_DAYS * 86400` (7 ngày)
- Profile name từ JWT email claim: `chatgpt-<localpart>` (cùng convention với chatgpt-onboard-card)
- HTTP 401 từ captcha-solver → log warning, không crash (admin re-onboard manually)

```python
def _decode_jwt_payload(token: str) -> dict | None:
    _, payload_b64, _ = token.split(".", 2)
    pad = "=" * (-len(payload_b64) % 4)
    return json.loads(base64.urlsafe_b64decode(payload_b64 + pad))

def _profile_for_email(email: str) -> str:
    local = email.split("@", 1)[0] or "default"
    safe = "".join(c if c.isalnum() or c == "-" else "-" for c in local)
    return f"chatgpt-{safe}"
```

### Cloudflare Worker pattern bypass VN geo-block

`generativelanguage.googleapis.com` chặn IP VN. Worker fetch lại từ edge US/SG → unblocked. File: [deploy/cloudflare-gemini-proxy.js](deploy/cloudflare-gemini-proxy.js).

Key tricks:
- Strip Cloudflare-injected headers (`cf-connecting-ip`, `cf-ipcountry`, `x-forwarded-*`, `x-real-ip`) trước khi fetch upstream
- Force clean User-Agent: `google-genai-sdk/0.1 gl-node/22.0.0` để Google không detect là bot
- Optional shared-secret: env `PROXY_TOKEN` → require header `X-Proxy-Token` hoặc query `?proxy_token=` (tránh ai cũng dùng được, hết quota free 100k req/day)
- Bỏ `transfer-encoding`/`connection`/`content-encoding` ở response (Worker sẽ tự re-encode)

Mọi call site Gemini trong chatgpt2api honor `providers.gemini_free.base_url`:

```python
def _gemini_base_url() -> str:
    cfg = (config.data.get("providers") or {}).get("gemini_free") or {}
    base = str(cfg.get("base_url") or "").rstrip("/")
    if base:
        if not base.endswith("/v1beta"):
            base = base + "/v1beta"
        return base
    return "https://generativelanguage.googleapis.com/v1beta"
```

Patched ở 6 file: [services/providers/gemini_free.py](services/providers/gemini_free.py), [services/image_providers/gemini_image.py](services/image_providers/gemini_image.py), [services/image_providers/veo_video.py](services/image_providers/veo_video.py), [services/search_service.py](services/search_service.py), [services/protocol/openai_v1_models.py](services/protocol/openai_v1_models.py), [services/protocol/openai_v1_image_generations.py](services/protocol/openai_v1_image_generations.py).

---

## 5. Quy trình deploy + verify (chuẩn)

---

## 5. Quy trình deploy + verify (chuẩn)

```bash
# 1. Push commit (CI auto-build via .github/workflows/*-build.yml)
git push origin HEAD

# 2. Wait build (5-8 min)
gh run watch <run-id> --repo TriTue2011/chatgpt2api --exit-status

# 3. Deploy
plink -ssh -pw '$PWD' -batch root@172.16.10.38 \
  "docker pull ghcr.io/tritue2011/<image>:latest && \
   docker rm -f <name> && \
   docker run -d --name <name> --restart unless-stopped \
     -p <port>:<port> -v /opt/<name>-data:/data \
     -e <ENV_VAR>=<value> \
     ghcr.io/tritue2011/<image>:latest"

# 4. Verify health
curl -s -o /dev/null -w '%{http_code}\n' http://172.16.10.38:<port>/health \
  -H 'Authorization: Bearer <key>'

# 5. E2E test endpoint với file body (tránh shell escape Unicode/quote)
curl -sS -X POST http://172.16.10.38:<port>/v1/<endpoint> \
  -H 'Authorization: Bearer <key>' -H 'Content-Type: application/json' \
  -d @/d/Chatgpt/_test_<feature>.json --max-time <secs> \
  -w "\nHTTP %{http_code} time=%{time_total}s\n" | tail -10
```

### Disk full nguy hiểm

Khi pull image mới mà disk full → `no space left on device` → container vẫn create với ID nhưng start fail. **Always** clean trước khi pull image lớn:

```bash
docker image prune -af   # gỡ untagged
docker container prune -f  # gỡ stopped
df -h /                  # verify > 5GB free
```

---

## 6. Service-specific notes

### Captcha-solver CLI (host-side, không cần Python local)

```bash
# Install wrapper
sudo cp captcha-solver/bin/cs-cli /usr/local/bin/cs-cli && chmod +x /usr/local/bin/cs-cli
# Optional remote target
export CS_HOST=root@172.16.10.38

# Onboarding Flow (Google Labs Flow image gen)
cs-cli onboard         <profile> <google-email> <google-password>

# ChatGPT-via-Google → scrape JWT free → paste vào chatgpt2api accounts
cs-cli chatgpt-onboard <profile> <google-email> <google-password>

# Gemini Web onboard
cs-cli gemini-web-onboard <profile> <google-email> <google-password>

# Capability calls
cs-cli gemini-web-chat   <profile> "<prompt>"
cs-cli gemini-web-image  <profile> "<prompt>"  [count]
cs-cli gemini-web-music  <profile> "<prompt>"
cs-cli gemini-web-vision <profile> <image-url-or-data> ["<prompt>"]
cs-cli chatgpt-web-chat   <profile> "<prompt>"
cs-cli chatgpt-web-image  <profile> "<prompt>"
cs-cli chatgpt-web-vision <profile> <image-url> ["<prompt>"]

# Diagnostics
cs-cli list / status <profile> / close <profile>
```

### chatgpt2api OpenAI-compat clients

```python
# Client sống ở máy IP bất kỳ — chỉ cần reach 172.16.10.38:3030
from openai import OpenAI
client = OpenAI(api_key="AnhNhi@0610", base_url="http://172.16.10.38:3030/v1")

# Force ChatGPT free path (vs codex)
client.chat.completions.create(model="chatgpt/free/auto", messages=[...])
# Force Codex path
client.chat.completions.create(model="chatgpt/codex/auto", messages=[...])
# Gemini Web (DOM scrape gemini.google.com) — auto vision/image qua model prefix
client.chat.completions.create(model="gmw/chat", messages=[...])
client.chat.completions.create(model="gmw/chat", messages=[
    {"role":"user","content":[
        {"type":"text","text":"phân tích ảnh"},
        {"type":"image_url","image_url":{"url":"https://..."}}
    ]}
])  # tự route /analyze-image, label "gmw/vision"
client.images.generate(model="gmw/image", prompt="...", n=1)
# ChatGPT Web (DOM scrape chatgpt.com) — same prefix family
client.chat.completions.create(model="cgw/chat", messages=[...])
client.images.generate(model="cgw/image", prompt="...", n=1)
# Flow image gen (Google Labs)
client.images.generate(model="flow/auto", prompt="...", n=1)
```

---

## 7. Probe templates (copy-paste vào /v1/browser/run)

### Find selector cho button by aria-label / text

```json
{
  "profile": "<profile>",
  "url": "<page-url>",
  "headless": false,
  "timeout": 30,
  "wait_for": "body",
  "script": "(async () => { for (let i = 0; i < 20; i++) { if (document.querySelector('[contenteditable=true]')) break; await new Promise(r => setTimeout(r, 500)); } return {url: location.href, btns: Array.from(document.querySelectorAll('button')).filter(b => b.offsetWidth > 0).slice(0, 30).map(b => ({label: b.getAttribute('aria-label'), text: (b.innerText||'').slice(0,40), data_testid: b.getAttribute('data-testid')}))}; })()"
}
```

### Inspect menu items sau khi click +

```json
{
  "profile": "<profile>",
  "url": "<page-url>",
  "headless": false,
  "timeout": 30,
  "wait_for": "body",
  "script": "(async () => { await new Promise(r => setTimeout(r, 2000)); document.querySelector('button[aria-label*=\"Nội dung\"]').click(); await new Promise(r => setTimeout(r, 1500)); return {items: Array.from(document.querySelectorAll('.cdk-overlay-pane button, [role=menu] [role=menuitem]')).filter(e => e.offsetWidth > 0).map(e => (e.innerText||'').slice(0,40).trim()).filter(t => t)}; })()"
}
```

### Confirm logged-in account on profile

```json
{
  "profile": "<profile>",
  "url": "https://myaccount.google.com",
  "headless": false,
  "timeout": 30,
  "wait_for": "body",
  "script": "({email: document.querySelector('meta[name=\"og-profile-acct\"]')?.content, title: document.title})"
}
```

---

## 8. Suy nghĩ tổng quát

1. **Probe → Hypothesis → Fix → Verify.** Đừng skip step 1.
2. **Conservative defaults thường gây pain.** Threshold (24KB, 60s timeout, 3 retries) phải test với real-world data.
3. **Multi-selector fallback** cho mọi DOM interaction — UI A/B tests đổi text/aria-label liên tục.
4. **OpenAI-compat wrapping** là cách rẻ nhất expose internal services cho ecosystem (HA, n8n, LiteLLM, ...).
5. **Profile data persist > convenience.** Mount mount path đúng + check sau redeploy.
6. **Anti-bot reality**: Google/OpenAI detect headless rất tốt. Headful + Xvfb + noVNC stable hơn nhiều so với headless + stealth args.
7. **Log everything** với event-prefixed structured JSON. `grep -iE "(pattern)"` trên log lúc debug tiết kiệm hàng giờ.
8. **CLI > UI** cho power-user / API-first deployment. UI là wrapper convenience.
9. **Auto-detect content shape > thêm endpoint mới.** Cùng `gmw/chat` lo cả vision + text bằng `_last_user_image()` reverse-scan, đừng bắt user gọi `gmw/vision` riêng.
10. **Mount path mismatch là silent killer.** Container code đọc `/app/data` (default) nhưng mount `-v xx:/data` → mọi thứ ghi vào layer ephemeral, redeploy mất sạch. Luôn `docker exec ... ls -la /data /app/data` để verify.

---

## 9. Outstanding (state 2026-05-24)

### Đã ship (8/8 batch + 4 tasks tiếp theo)

- **8a/8b** — Vision + image gen qua OpenAI multimodal block: `gmw/vision`, `cgw/vision`, `gmw/image`, `cgw/image`
- **8c** — UI cards [gemini-web-card.tsx](web/src/app/settings/components/gemini-web-card.tsx), [chatgpt-web-card.tsx](web/src/app/settings/components/chatgpt-web-card.tsx) registered ở settings page
- **9** — JWT auto-refresh: captcha-solver `/v1/chatgpt/{profile}/refresh-jwt` + chatgpt2api scheduler quét mỗi 6h, threshold 7 days
- **10** — Gemini VN bypass: [deploy/cloudflare-gemini-proxy.js](deploy/cloudflare-gemini-proxy.js) Worker + 6 call site honor `providers.gemini_free.base_url`
- **11** — Backup interval presets (Mỗi giờ / 6h / Hằng ngày / Hằng tuần)

### Còn pending

- ~~**Vision trên free path**~~ ✅ fixed 2026-05-25 — `_api_messages_to_conversation_messages` accept `image_url`/`input_image` blocks, dùng `_upload_image()` có sẵn.
- **Cloudflare Worker chưa deploy thực tế** — code sẵn ở `deploy/cloudflare-gemini-proxy.js`, cần `wrangler deploy` + paste URL vào Settings.
- **Profile Gemini chưa có Imagen** trên test account → `gmw/image` fail "Không bật được tool 'Tạo hình ảnh'". Cần account khác có quota.
- **HA `conversation.ai_agent_ai_agent` template prompt** trả greeting wrap thay vì straight tool_call — nằm ngoài chatgpt2api, ở config HA.

---

*Last updated: 2026-05-24 (after batch 8/9/10/11 + HA E2E test report)*
