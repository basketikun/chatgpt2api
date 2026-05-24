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

`FREE_PAYLOAD_LIMIT = 24_000` (chatgpt2api) làm router redirect khỏi ChatGPT free + RTK truncate system prompt 26.7KB của HA → AI hallucinate tên entity. Raise 80KB → fix cả 2 issue. **Luôn benchmark giới hạn thực tế trước khi đặt conservative cap.**

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
# Gemini Web (DOM scrape gemini.google.com)
client.chat.completions.create(model="gmw/chat", messages=[...])
# ChatGPT Web (DOM scrape chatgpt.com)
client.chat.completions.create(model="cgw/chat", messages=[...])
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

---

*Last updated: 2026-05-24 (after the 8-task batch closeout)*
