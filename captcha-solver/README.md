# captcha-solver

Patchright-based browser sandbox that turns "I need a CAPTCHA token / a
logged-in browser" into an HTTP call. Designed to run next to chatgpt2api
and vn-mcp-hub so any of them — chat completions, Home Assistant
automations, n8n workflows, Telegram bots — can outsource captcha work
and persistent Google logins.

## Table of contents

- [What it does](#what-it-does)
- [Endpoints](#endpoints)
- [Deploy](#deploy)
- [Google Labs Flow image generation](#google-labs-flow-image-generation)
  - [One-time per Google account](#one-time-per-google-account)
  - [Use from chatgpt2api](#use-from-chatgpt2api-recommended)
  - [Use from Home Assistant](#use-from-home-assistant)
  - [Use from n8n](#use-from-n8n)
  - [Use raw with curl](#use-raw-with-curl)
  - [Multiple Google accounts](#multiple-google-accounts)
- [phatnguoi.vn Turnstile lookup](#phatnguoivn-turnstile-lookup)
- [Manual login flow](#manual-login-flow)
- [Environment variables](#environment-variables)
- [Troubleshooting](#troubleshooting)

## What it does

- `phatnguoi.vn` gates every lookup behind Cloudflare Turnstile.
- `csgt.bocongan.gov.vn` gates lookups behind reCAPTCHA v3.
- `labs.google/fx/tools/flow/...` needs a logged-in Google session that
  survives across automated calls.

Spinning up a Patchright runtime per call is too slow (~3 s cold start), so
this service keeps long-lived browser contexts per **profile**. A profile
is just a Chromium `user-data-dir` mounted under `./data/profiles/<name>/`
— cookies, localStorage and IndexedDB persist across restarts (often for
months until the upstream forces a re-auth).

## Endpoints

All `/v1/*` calls require `Authorization: Bearer $CAPTCHA_SOLVER_API_KEY`.

```
POST /v1/solve/turnstile           {url, sitekey?, profile?, headless?, timeout?}
POST /v1/solve/recaptcha3          {url, sitekey, action, profile?, headless?}
POST /v1/solve/recaptcha2          {url, profile?, headless?}
POST /v1/browser/run               {url, script?, wait_for?, profile?, headless?}
POST /v1/forms/phatnguoi           {plate, vehicle_type?, profile?}
POST /v1/google/flow/generate-image {project_id, prompt, return_binary?, ...}
POST /v1/session/manual-login      {url, profile}   ← open in noVNC for human login
GET  /v1/session/list                                ← list saved profiles
GET  /v1/session/{profile}/status
POST /v1/session/{profile}/close
GET  /health                                         ← unauth liveness probe
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
| `6080` | noVNC web UI (manual login) | proxy through Cloudflare Tunnel or SSH tunnel — do NOT expose to the open internet |

## Google Labs Flow image generation

Free-tier image generation through `labs.google/fx/tools/flow` driven as a
real user via Patchright. No paid solver, no API key, no cost beyond the
Google account's Flow quota (~few dozen images/day on free tier).

### One-time per Google account

```bash
# 1) open a headful login session
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"google-fx","url":"https://labs.google/fx/vi/tools/flow"}'

# 2) open http://YOUR_SERVER_IP:6080/vnc.html?host=YOUR_SERVER_IP&port=6080&autoconnect=1
#    in your laptop browser, sign in to Google in the Chromium window,
#    open a Flow project once, then close the tab.
#    Cookies persist in ./data/profiles/google-fx/ for months.

# 3) copy the project_id from the URL bar:
#    https://labs.google/fx/vi/tools/flow/project/<PROJECT_ID>
```

### Use from chatgpt2api (recommended)

The `flow` provider is built into chatgpt2api. Add to
`/opt/chatgpt2api-data/config.json`:

```json
"providers": {
  "flow": {
    "enabled": true,
    "captcha_solver_url": "http://YOUR_SERVER_IP:8010",
    "captcha_solver_api_key": "<bearer key>",
    "accounts": [
      {"profile": "google-fx", "project_id": "<UUID>", "label": "Main"}
    ]
  }
}
```

Restart chatgpt2api. Then use it like any OpenAI image model:

```bash
# JSON response (URL pointing to a chatgpt2api-hosted copy of the image)
curl -X POST http://YOUR_SERVER_IP:3030/v1/images/generations \
     -H "Authorization: Bearer <chatgpt2api-key>" \
     -H "Content-Type: application/json" \
     -d '{
           "model": "flow/banana-2",
           "prompt": "a cyberpunk cat playing piano",
           "n": 1,
           "response_format": "url"
         }'
```

Model aliases (all map to Flow's `imageModelName`):

| chatgpt2api model | Flow model | Notes |
|---|---|---|
| `flow/banana-2` | `NARWHAL` | Nano Banana 2 — default, fastest |
| `flow/banana-pro` | `NANO_BANANA_PRO` | higher quality, slower |
| `flow/imagen-4` | `IMAGEN_4` | Imagen 4 |
| `flow/<anything>` | uppercased, forwarded | escape hatch for new models |

### Use from Home Assistant

The most practical pattern is **`shell_command` + Picture entity** so the
JPEG bytes land in `/config/www/` and the dashboard can display them
without a second HTTP round-trip.

**`/config/secrets.yaml`**:

```yaml
captcha_solver_key: "<your captcha-solver bearer>"
```

**`/config/configuration.yaml`**:

```yaml
homeassistant:
  allowlist_external_dirs:
    - /config/www

input_text:
  flow_prompt:
    name: Mô tả ảnh
    max: 500

shell_command:
  flow_generate: >
    curl -s -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image
    -H "Authorization: Bearer !secret captcha_solver_key"
    -H "Content-Type: application/json"
    -d '{"project_id":"<UUID>","prompt":"{{ prompt }}","return_binary":true,
         "aspect_ratio":"IMAGE_ASPECT_RATIO_LANDSCAPE",
         "model":"NANO_BANANA_PRO","count":1}'
    --max-time 180
    -o /config/www/flow_latest.jpg
```

**Optional params** (all default to the strongest setup):

| Param | Default | Other values |
|---|---|---|
| `model` | `NANO_BANANA_PRO` | `NARWHAL` (Nano Banana 2), `IMAGEN_4` |
| `aspect_ratio` | `IMAGE_ASPECT_RATIO_LANDSCAPE` (16:9) | `IMAGE_ASPECT_RATIO_SQUARE` (1:1), `IMAGE_ASPECT_RATIO_LANDSCAPE_4_3` (4:3), `IMAGE_ASPECT_RATIO_PORTRAIT_3_4` (3:4), `IMAGE_ASPECT_RATIO_PORTRAIT` (9:16) |
| `count` | `1` | 2 / 3 / 4 |

Want a UI in Home Assistant to pick model / aspect / count without
editing YAML? Use `input_select` entities:

```yaml
input_select:
  flow_model:
    name: Model
    options: [NANO_BANANA_PRO, NARWHAL, IMAGEN_4]
    initial: NANO_BANANA_PRO
  flow_aspect:
    name: Tỷ lệ
    options:
      - "IMAGE_ASPECT_RATIO_LANDSCAPE"       # 16:9
      - "IMAGE_ASPECT_RATIO_LANDSCAPE_4_3"   # 4:3
      - "IMAGE_ASPECT_RATIO_SQUARE"          # 1:1
      - "IMAGE_ASPECT_RATIO_PORTRAIT_3_4"    # 3:4
      - "IMAGE_ASPECT_RATIO_PORTRAIT"        # 9:16
    initial: "IMAGE_ASPECT_RATIO_LANDSCAPE"
  flow_count:
    name: Số ảnh
    options: ["1", "2", "3", "4"]
    initial: "1"

shell_command:
  flow_generate_v2: >
    curl -s -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image
    -H "Authorization: Bearer !secret captcha_solver_key"
    -H "Content-Type: application/json"
    -d '{"project_id":"<UUID>","prompt":"{{ prompt }}","return_binary":true,
         "model":"{{ states('input_select.flow_model') }}",
         "aspect_ratio":"{{ states('input_select.flow_aspect') }}",
         "count":{{ states('input_select.flow_count') | int }}}'
    --max-time 180
    -o /config/www/flow_latest.jpg
```

**Dashboard card** (vertical stack: input → button → image):

```yaml
type: vertical-stack
cards:
  - type: entities
    entities:
      - input_text.flow_prompt
  - type: button
    name: 🎨 Tạo ảnh
    tap_action:
      action: call-service
      service: shell_command.flow_generate
      service_data:
        prompt: "{{ states('input_text.flow_prompt') }}"
  - type: picture
    image: /local/flow_latest.jpg
```

→ type the prompt, tap the button, wait ~40 s, image appears.

**Voice command** (if Assist is set up):

```yaml
conversation:
  intents:
    GenerateImage:
      - "tạo ảnh {prompt}"
      - "vẽ {prompt}"

intent_script:
  GenerateImage:
    speech:
      text: "Đang vẽ {{ prompt }}, đợi một phút nhé"
    action:
      - service: shell_command.flow_generate
        data:
          prompt: "{{ prompt }}"
```

**Send to Telegram** after generation (chains via automation):

```yaml
automation:
  - alias: "Flow → Telegram"
    trigger:
      platform: state
      entity_id: input_button.gen_image
    action:
      - service: shell_command.flow_generate
        data:
          prompt: "{{ states('input_text.flow_prompt') }}"
      - delay: "00:00:45"
      - service: notify.telegram
        data:
          message: "🎨 {{ states('input_text.flow_prompt') }}"
          data:
            photo:
              - file: /config/www/flow_latest.jpg
```

### Use from n8n

The captcha-solver returns binary JPEG when you set `return_binary: true`,
so the standard **HTTP Request** node hands you a file you can pipe
directly into Telegram / Discord / Drive / etc.

**Single HTTP Request node config**:

| Field | Value |
|---|---|
| Method | `POST` |
| URL | `http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image` |
| Authentication | Header Auth → `Authorization: Bearer <key>` |
| Send Headers | ✅ `Content-Type: application/json` |
| Send Body | ✅ JSON |
| Body JSON | see below |
| Response Format | **File** |
| Put Output In Field | `data` |
| Timeout | `180000` ms |

Body JSON (default — Nano Banana Pro, 16:9, 1 image):
```json
{
  "project_id": "{{ $json.project_id }}",
  "prompt": "{{ $json.prompt }}",
  "return_binary": true
}
```

Body JSON with all overrides:
```json
{
  "project_id": "{{ $json.project_id }}",
  "prompt": "{{ $json.prompt }}",
  "model": "NANO_BANANA_PRO",
  "aspect_ratio": "IMAGE_ASPECT_RATIO_LANDSCAPE",
  "count": 1,
  "return_binary": true
}
```

**Complete workflow: Form trigger → generate → Telegram** (copy-paste into n8n):

```json
{
  "name": "Flow image to Telegram",
  "nodes": [
    {
      "parameters": {
        "formTitle": "Tạo ảnh bằng Google Flow",
        "formFields": {
          "values": [
            {"fieldLabel": "Prompt", "fieldType": "textarea", "requiredField": true}
          ]
        }
      },
      "type": "n8n-nodes-base.formTrigger",
      "typeVersion": 2.3,
      "position": [0, 0],
      "id": "trigger",
      "name": "Form",
      "webhookId": "flow-gen"
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image",
        "sendHeaders": true,
        "headerParameters": {
          "parameters": [
            {"name": "Authorization", "value": "Bearer YOUR_CAPTCHA_SOLVER_KEY"},
            {"name": "Content-Type", "value": "application/json"}
          ]
        },
        "sendBody": true,
        "specifyBody": "json",
        "jsonBody": "={\n  \"project_id\": \"YOUR_FLOW_PROJECT_ID\",\n  \"prompt\": \"{{ $json.Prompt }}\",\n  \"return_binary\": true\n}",
        "options": {
          "response": {"response": {"responseFormat": "file", "outputPropertyName": "data"}},
          "timeout": 180000
        }
      },
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 4.3,
      "position": [240, 0],
      "id": "gen",
      "name": "Generate image"
    },
    {
      "parameters": {
        "chatId": "YOUR_TELEGRAM_CHAT_ID",
        "binaryData": true,
        "operation": "sendPhoto",
        "additionalFields": {
          "caption": "={{ $('Form').item.json.Prompt }}"
        }
      },
      "type": "n8n-nodes-base.telegram",
      "typeVersion": 1.2,
      "position": [480, 0],
      "id": "tg",
      "name": "Send to Telegram",
      "credentials": {"telegramApi": {"id": "REPLACE", "name": "Telegram"}}
    }
  ],
  "connections": {
    "Form": {"main": [[{"node": "Generate image", "type": "main", "index": 0}]]},
    "Generate image": {"main": [[{"node": "Send to Telegram", "type": "main", "index": 0}]]}
  }
}
```

Replace the three placeholders (`YOUR_SERVER_IP`,
`YOUR_CAPTCHA_SOLVER_KEY`, `YOUR_FLOW_PROJECT_ID`,
`YOUR_TELEGRAM_CHAT_ID`) and wire up your Telegram credential. Activate
the workflow, open its Form URL on your phone, type a prompt → ~45 s
later Telegram delivers the image.

**Variations**:

- **Save to Google Drive** instead: replace the Telegram node with the
  **Google Drive → Upload** node, source `data` (binary).
- **Post to Discord webhook**: HTTP Request POST to Discord webhook URL
  with form-data field `file` = `={{ $binary.data }}`.
- **Email the image**: use the **Send Email** node with attachment from
  `$binary.data`.

**Loop with multiple prompts** (batch generation): drop a **Split In
Batches** node between Form and HTTP Request, set batch size 1 — n8n
will sequentially generate one image per prompt and chain them all to
Telegram.

**Use a different account per request**: add another HTTP Request node
with a different `profile` and `project_id` in the body, or rely on
chatgpt2api's built-in round-robin by routing through
`http://YOUR_SERVER_IP:3030/v1/images/generations` with `model:"flow/banana-2"`
instead of hitting captcha-solver directly.

### Use raw with curl

```bash
# Binary JPEG straight to file
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"<UUID>","prompt":"a samurai cat","return_binary":true}' \
     -o image.jpg
# response headers carry metadata: x-flow-model, x-flow-seed, x-flow-elapsed-ms

# JSON with CDN URL
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"<UUID>","prompt":"a samurai cat"}'
# → {"images":[{"url":"https://flow-content.google/image/...","seed":...}],"elapsed_ms":45000}
```

### Multiple Google accounts

Each account = one `profile` directory. To add a second account:

```bash
# 1) open a NEW manual-login session with a NEW profile name
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"google-fx-2","url":"https://labs.google/fx/vi/tools/flow"}'

# 2) open noVNC → log in to the second Google account → open a Flow project
#    → copy its project_id from the URL

# 3) append to config.json:
```

```json
"providers": {
  "flow": {
    "accounts": [
      {"profile":"google-fx",   "project_id":"<uuid-1>", "label":"Main"},
      {"profile":"google-fx-2", "project_id":"<uuid-2>", "label":"Backup"}
    ]
  }
}
```

Restart chatgpt2api. The provider **round-robins** between accounts and
marks an account "cooldown" for an hour on quota/429 errors.

**Concurrency**:
- Different accounts → parallel (each profile is an independent Chromium context)
- Same account → serialised (profile lock prevents cookie corruption)

So one container handles N accounts comfortably. You only need multiple
containers if you want each account on a different outbound IP (e.g.
behind separate proxies).

List which profiles already exist:

```bash
curl http://YOUR_SERVER_IP:8010/v1/session/list \
     -H "Authorization: Bearer $API_KEY"
```

## phatnguoi.vn Turnstile lookup

```bash
# Direct lookup (uses the 'phatnguoi' profile by default)
curl -X POST http://YOUR_SERVER_IP:8010/v1/forms/phatnguoi \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"plate":"99A40201","vehicle_type":1}'
```

`vehicle_type`: 1 = ô tô, 2 = xe máy, 3 = xe điện.

vn-mcp-hub's `vn_phat_nguoi` MCP also uses this endpoint when env
`CAPTCHA_SOLVER_URL` is set — so any chatgpt2api chat completion that
calls `check_traffic_violation` will fall back here when the JSON APIs
return empty.

The phatnguoi.vn Turnstile is strict; one-time noVNC login required (same
flow as Google Flow above) using profile `phatnguoi`. After that, cookies
keep working for a few hours to a few days.

## Manual login flow

Any site that gates content behind a real-user session can be primed once
via noVNC, then driven headlessly with the saved profile:

```bash
# 1) open the site in a headful Chromium tab visible via noVNC
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"some-name","url":"https://example.com/login"}'

# 2) point a browser at http://YOUR_SERVER_IP:6080/vnc.html
#    → log in / click whatever needs human input

# 3) headless calls with the same profile inherit the cookies
curl -X POST http://YOUR_SERVER_IP:8010/v1/browser/run \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"some-name","url":"https://example.com/protected","wait_for":"main","script":"document.title"}'
```

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `CAPTCHA_SOLVER_API_KEY` | `change-me` | Bearer token required on every `/v1/*` call. |
| `CAPTCHA_SOLVER_DATA_DIR` | `/data` | Where profile user-data-dirs live. |
| `CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL` | (compose default) | URL shown back in `/v1/session/manual-login` responses. Use whatever your phone/browser can actually reach. |
| `CAPTCHA_SOLVER_SOLVE_TIMEOUT` | `90` | Per-solve hard timeout (seconds). |
| `CAPTCHA_SOLVER_2CAPTCHA_KEY` | _(unset)_ | If set, falls back to 2captcha when self-solve fails on Turnstile. |

## Troubleshooting

**`Could not capture ya29 token. Profile likely not logged in.`**
The Google profile has no session cookies. Re-run `/v1/session/manual-login`
with the matching profile name and sign in via noVNC.

**`Flow UI never hydrated (timeout).`**
Google has logged the profile out (~once every several months on free
tier). Re-run manual login.

**`Did not observe flowMedia POST within timeout.`**
The Flow UI changed (button moved, prompt input became a different
element). Open noVNC and watch what actually happens when you click
"Tạo" manually. Update selectors in `src/solvers/flow_google.py` if
needed.

**`turnstile solve timed out` (on phatnguoi.vn specifically)**
Cloudflare Turnstile refuses to render the widget for the server's IP.
This is expected on datacenter IPs. Workarounds:
1. Tick the captcha manually once via noVNC — cookies last hours
2. Set `CAPTCHA_SOLVER_2CAPTCHA_KEY` for paid fallback
3. Run the container behind a residential proxy

**`Connection refused` from chatgpt2api → captcha-solver**
The chatgpt2api container can't reach `localhost:8010` (that's its own
localhost). Use the host IP (`http://YOUR_SERVER_IP:8010`) or put both
containers on a shared Docker network and use the container name
(`http://captcha-solver:8010`).
