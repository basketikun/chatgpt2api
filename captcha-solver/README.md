# captcha-solver

Patchright-based browser sandbox that turns "I need a CAPTCHA token / a
logged-in browser" into an HTTP call. Designed to run next to chatgpt2api
and vn-mcp-hub so any of them can outsource captcha work and persistent
Google logins.

## Why

- `phatnguoi.vn` gates every lookup behind Cloudflare Turnstile.
- `csgt.bocongan.gov.vn` gates lookups behind reCAPTCHA v3.
- `labs.google/fx/tools/flow/...` needs a logged-in Google session that
  survives across automated calls.

Spinning up a Patchright runtime per call is too slow (~3 s cold start), so
this service keeps long-lived browser contexts per **profile**. A profile
is just a chromium `user-data-dir` mounted under `./data/profiles/<name>/`
— cookies, localStorage and IndexedDB persist across restarts.

## Endpoints (all require `Authorization: Bearer $CAPTCHA_SOLVER_API_KEY`)

```
POST /v1/solve/turnstile           {url, sitekey?, profile?, headless?, timeout?}
POST /v1/solve/recaptcha3          {url, sitekey, action, profile?, headless?}
POST /v1/solve/recaptcha2          {url, profile?, headless?}
POST /v1/browser/run               {url, script?, wait_for?, profile?, headless?}
POST /v1/forms/phatnguoi           {plate, vehicle_type?, profile?}
POST /v1/google/flow/generate-image {project_id, prompt, return_binary?, ...}
POST /v1/session/manual-login      {url, profile}   ← open in noVNC for human login
GET  /v1/session/{profile}/status
POST /v1/session/{profile}/close
GET  /health                                      ← unauth liveness probe
```

## Google Labs Flow image generation

Free-tier image generation through `labs.google/fx/tools/flow` driven as a
real user via Patchright. No paid solver, no API key, no cost beyond the
Google account's Flow quota.

### One-time setup (~1 minute)

```bash
# 1) open a headful login session
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"google-fx","url":"https://labs.google/fx/vi/tools/flow"}'

# 2) open http://YOUR_SERVER_IP:6080/vnc.html?host=172.16.10.38&port=6080&autoconnect=1
#    in a browser, sign in to Google in the Chromium window, then close the tab.
#    Cookies persist in /data/profiles/google-fx/ for months.
```

### Generate (JSON response with image URL)

```bash
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "project_id": "54468d77-02ff-4a06-bb81-05a7d1111544",
           "prompt": "a samurai cat in feudal Japan, cinematic"
         }'
# → {"images":[{"url":"https://flow-content.google/image/...","seed":...}], "elapsed_ms":45000}
```

### Generate (binary PNG straight back — for Home Assistant / n8n)

```bash
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"...","prompt":"...","return_binary":true}' \
     -o image.png
```

### Home Assistant integration

Add to `configuration.yaml`:

```yaml
rest_command:
  flow_generate:
    url: "http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image"
    method: POST
    headers:
      Authorization: !secret captcha_solver_key   # "Bearer ..."
      Content-Type: "application/json"
    payload: >
      {
        "project_id": "54468d77-02ff-4a06-bb81-05a7d1111544",
        "prompt": "{{ prompt }}",
        "return_binary": true
      }
    timeout: 180
```

Call from automations:

```yaml
service: rest_command.flow_generate
data:
  prompt: "a cyberpunk cat playing piano, neon lights"
```

### n8n integration

Add an **HTTP Request** node:

- Method: `POST`
- URL: `http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image`
- Authentication: Header Auth (`Authorization: Bearer <key>`)
- Body: JSON
  ```json
  {
    "project_id": "{{ $json.project_id }}",
    "prompt": "{{ $json.prompt }}",
    "return_binary": true
  }
  ```
- Response Format: **File** (binary). The image lands in
  `$binary.data` and you can pipe straight into "Convert to File" / upload to
  Drive / send via Telegram, etc.

## Manual-login flow (Google labs.fx, n8n auth, etc.)

```bash
# 1) Tell the service to open a Chromium window inside Xvfb pointed at the site.
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $CAPTCHA_SOLVER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile": "google-fx", "url": "https://labs.google/fx/vi/tools/flow"}'

# 2) Open http://YOUR_SERVER_IP:6080/vnc.html in your browser. You will see
#    the Chromium window. Click through Google's sign-in flow once.

# 3) Later, automated calls reuse the cookies headlessly:
curl -X POST http://YOUR_SERVER_IP:8010/v1/browser/run \
     -H "Authorization: Bearer $CAPTCHA_SOLVER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "profile": "google-fx",
           "url": "https://labs.google/fx/vi/tools/flow",
           "wait_for": "main",
           "script": "document.title"
         }'
```

## Quick Turnstile solve (phatnguoi.vn)

```bash
curl -X POST http://YOUR_SERVER_IP:8010/v1/solve/turnstile \
     -H "Authorization: Bearer $CAPTCHA_SOLVER_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
           "url": "https://phatnguoi.vn/",
           "sitekey": "0x4AAAAAADJ42iX8Yvx1UXWe",
           "profile": "phatnguoi"
         }'
# → {"token": "0.xxx...", "expires_at": 1779.., "profile": "phatnguoi"}
```

## Deploy

### Option A — pull prebuilt image from GHCR (recommended)

```bash
mkdir -p captcha-solver/data && cd captcha-solver
curl -O https://raw.githubusercontent.com/TriTue2011/chatgpt2api/main/captcha-solver/docker-compose.yml

cat > .env <<EOF
CAPTCHA_SOLVER_API_KEY=$(openssl rand -hex 16)
# replace YOUR_SERVER_IP with whatever address your phone/browser can hit
CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL=http://YOUR_SERVER_IP:6080/vnc.html?host=YOUR_SERVER_IP&port=6080&autoconnect=1
EOF

docker compose up -d
```

The image is auto-built by `.github/workflows/captcha-solver-build.yml`
on every push to `main`, tagged `ghcr.io/<owner>/captcha-solver:latest`.

### Option B — build locally

```bash
git clone https://github.com/TriTue2011/chatgpt2api.git
cd chatgpt2api/captcha-solver
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

First build takes ~3 min (Chromium + Patchright download). Subsequent
restarts are instant.

### Ports

| Port | Purpose | Expose publicly? |
|---|---|---|
| `8010` | FastAPI (API key required) | only to trusted clients |
| `6080` | noVNC web UI (for manual login) | only when you actually need to log in — proxy through Cloudflare Tunnel or SSH tunnel; do NOT expose to the open internet |

## Environment

| Variable | Default | What it does |
|---|---|---|
| `CAPTCHA_SOLVER_API_KEY` | `change-me` | Bearer token required on every `/v1/*` call. |
| `CAPTCHA_SOLVER_DATA_DIR` | `/data` | Where profile user-data-dirs live. |
| `CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL` | (compose default) | URL shown back in `/v1/session/manual-login` responses. |
| `CAPTCHA_SOLVER_SOLVE_TIMEOUT` | `90` | Per-solve hard timeout (seconds). |
