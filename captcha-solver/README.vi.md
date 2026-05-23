# captcha-solver

Sandbox trình duyệt dựa trên Patchright, biến "tôi cần token CAPTCHA / một trình duyệt đã đăng nhập" thành một lời gọi HTTP. Được thiết kế để chạy song song với chatgpt2api và vn-mcp-hub, giúp các tác nhân như chat completions, tự động hóa Home Assistant, quy trình n8n, bot Telegram... có thể ủy thác công việc giải CAPTCHA và duy trì phiên đăng nhập Google liên tục.

## Mục lục

- [Chức năng](#chức-năng)
- [Các endpoint](#các-endpoint)
- [Triển khai](#triển-khai)
- [Tạo ảnh với Google Labs Flow](#tạo-ảnh-với-google-labs-flow)
  - [Thiết lập một lần cho mỗi tài khoản Google](#thiết-lập-một-lần-cho-mỗi-tài-khoản-google)
  - [Dùng từ chatgpt2api (khuyến nghị)](#dùng-từ-chatgpt2api-khuyến-nghị)
  - [Dùng từ Home Assistant](#dùng-từ-home-assistant)
  - [Dùng từ n8n](#dùng-từ-n8n)
  - [Dùng trực tiếp với curl](#dùng-trực-tiếp-với-curl)
  - [Nhiều tài khoản Google](#nhiều-tài-khoản-google)
- [Tra cứu phạt nguội trên phatnguoi.vn (Turnstile)](#tra-cứu-phạt-nguội-trên-phatnguoivn-turnstile)
- [Luồng đăng nhập thủ công](#luồng-đăng-nhập-thủ-công)
- [Biến môi trường](#biến-môi-trường)
- [Xử lý sự cố](#xử-lý-sự-cố)

## Chức năng

- `phatnguoi.vn` chặn mọi lượt tra cứu bằng Cloudflare Turnstile.
- `csgt.bocongan.gov.vn` chặn tra cứu bằng reCAPTCHA v3.
- `labs.google/fx/tools/flow/...` yêu cầu phiên Google đã đăng nhập, duy trì liên tục qua các lần gọi tự động.

Khởi động runtime Patchright mới cho mỗi lần gọi quá chậm (~3 giây khởi nguội), nên dịch vụ này duy trì các browser context sống lâu dài theo **profile**. Một profile là một thư mục `user-data-dir` của Chromium được mount tại `./data/profiles/<tên>/` — cookie, localStorage và IndexedDB được giữ lại qua các lần khởi động lại (thường hàng tháng cho đến khi phía trên yêu cầu xác thực lại).

## Các endpoint

Tất cả các lời gọi `/v1/*` yêu cầu `Authorization: Bearer $CAPTCHA_SOLVER_API_KEY`.

```
POST /v1/solve/turnstile           {url, sitekey?, profile?, headless?, timeout?}
POST /v1/solve/recaptcha3          {url, sitekey, action, profile?, headless?}
POST /v1/solve/recaptcha2          {url, profile?, headless?}
POST /v1/browser/run               {url, script?, wait_for?, profile?, headless?}
POST /v1/forms/phatnguoi           {plate, vehicle_type?, profile?}
POST /v1/google/flow/generate-image {project_id, prompt, return_binary?, ...}
POST /v1/session/manual-login      {url, profile}   ← mở trong noVNC để người dùng đăng nhập
GET  /v1/session/list                                ← liệt kê các profile đã lưu
GET  /v1/session/{profile}/status
POST /v1/session/{profile}/close
GET  /health                                         ← kiểm tra liveness (không cần xác thực)
```

## Triển khai

### Phương án A — Kéo image dựng sẵn từ GHCR (khuyến nghị)

```bash
mkdir -p captcha-solver/data && cd captcha-solver
curl -O https://raw.githubusercontent.com/TriTue2011/chatgpt2api/main/captcha-solver/docker-compose.yml

cat > .env <<EOF
CAPTCHA_SOLVER_API_KEY=$(openssl rand -hex 16)
# thay YOUR_SERVER_IP bằng địa chỉ mà điện thoại/trình duyệt của bạn có thể truy cập
CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL=http://YOUR_SERVER_IP:6080/vnc.html?host=YOUR_SERVER_IP&port=6080&autoconnect=1
EOF

docker compose up -d
```

Image được tự động build bởi `.github/workflows/captcha-solver-build.yml` mỗi lần push lên `main`, được gắn tag `ghcr.io/<owner>/captcha-solver:latest`.

### Phương án B — Build cục bộ

```bash
git clone https://github.com/TriTue2011/chatgpt2api.git
cd chatgpt2api/captcha-solver
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

Lần build đầu mất ~3 phút (tải Chromium + Patchright). Các lần khởi động lại sau đó gần như tức thì.

### Cổng dịch vụ

| Cổng | Mục đích | Có nên mở công khai? |
|---|---|---|
| `8010` | FastAPI (yêu cầu API key) | Chỉ cho các client tin cậy |
| `6080` | noVNC web UI (đăng nhập thủ công) | Dùng qua Cloudflare Tunnel hoặc SSH tunnel — **KHÔNG** mở ra internet công cộng |

## Tạo ảnh với Google Labs Flow

Tạo ảnh miễn phí qua `labs.google/fx/tools/flow` được điều khiển như người dùng thực bằng Patchright. Không cần dịch vụ giải CAPTCHA trả phí, không cần API key, không mất chi phí ngoài hạn ngạch Flow của tài khoản Google (~vài chục ảnh/ngày với gói miễn phí).

### Thiết lập một lần cho mỗi tài khoản Google

```bash
# 1) Mở phiên đăng nhập có giao diện
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"google-fx","url":"https://labs.google/fx/vi/tools/flow"}'

# 2) Mở http://YOUR_SERVER_IP:6080/vnc.html?host=YOUR_SERVER_IP&port=6080&autoconnect=1
#    trên trình duyệt máy tính, đăng nhập Google trong cửa sổ Chromium,
#    mở một project Flow một lần rồi đóng tab lại.
#    Cookie được lưu trong ./data/profiles/google-fx/ trong nhiều tháng.

# 3) Sao chép project_id từ thanh địa chỉ:
#    https://labs.google/fx/vi/tools/flow/project/<PROJECT_ID>
```

### Dùng từ chatgpt2api (khuyến nghị)

Provider `flow` đã được tích hợp sẵn trong chatgpt2api. Thêm vào `/opt/chatgpt2api-data/config.json`:

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

Khởi động lại chatgpt2api. Sau đó dùng như model ảnh OpenAI thông thường:

```bash
# Phản hồi JSON (URL trỏ đến bản sao ảnh lưu trên chatgpt2api)
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

Tên model (đều ánh xạ tới `imageModelName` của Flow):

| Model chatgpt2api | Model Flow | Ghi chú |
|---|---|---|
| `flow/banana-2` | `NARWHAL` | Nano Banana 2 — mặc định, nhanh nhất |
| `flow/banana-pro` | `NANO_BANANA_PRO` | Chất lượng cao hơn, chậm hơn |
| `flow/imagen-4` | `IMAGEN_4` | Imagen 4 |
| `flow/<bất kỳ>` | Viết hoa và chuyển tiếp | Tùy chọn mở rộng cho model mới |

### Dùng từ Home Assistant

Cách thực tế nhất là dùng **`shell_command` + Picture entity** để byte JPEG được lưu vào `/config/www/` và dashboard có thể hiển thị trực tiếp mà không cần thêm một lần gọi HTTP nữa.

**`/config/secrets.yaml`**:

```yaml
captcha_solver_key: "<bearer key của captcha-solver>"
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
    -d '{"project_id":"<UUID>","prompt":"{{ prompt }}","return_binary":true}'
    --max-time 180
    -o /config/www/flow_latest.jpg
```

**Card Dashboard** (dọc: ô nhập → nút → ảnh):

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

→ Gõ prompt, nhấn nút, đợi ~40 giây, ảnh hiện ra.

**Lệnh giọng nói** (nếu đã cài đặt Assist):

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

**Gửi lên Telegram** sau khi tạo xong (kết hợp qua automation):

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

### Dùng từ n8n

captcha-solver trả về JPEG nhị phân khi bạn đặt `return_binary: true`, nên node **HTTP Request** tiêu chuẩn sẽ cho bạn một file có thể đưa thẳng vào Telegram / Discord / Drive / v.v.

**Cấu hình node HTTP Request đơn**:

| Trường | Giá trị |
|---|---|
| Method | `POST` |
| URL | `http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image` |
| Authentication | Header Auth → `Authorization: Bearer <key>` |
| Send Headers | ✅ `Content-Type: application/json` |
| Send Body | ✅ JSON |
| Body JSON | xem bên dưới |
| Response Format | **File** |
| Put Output In Field | `data` |
| Timeout | `180000` ms |

Body JSON:
```json
{
  "project_id": "{{ $json.project_id }}",
  "prompt": "{{ $json.prompt }}",
  "return_binary": true
}
```

**Workflow hoàn chỉnh: Form trigger → tạo ảnh → Telegram** (dán thẳng vào n8n):

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

Thay ba placeholder (`YOUR_SERVER_IP`, `YOUR_CAPTCHA_SOLVER_KEY`, `YOUR_FLOW_PROJECT_ID`, `YOUR_TELEGRAM_CHAT_ID`) và gắn credential Telegram. Kích hoạt workflow, mở URL Form trên điện thoại, gõ prompt → ~45 giây sau Telegram giao ảnh.

**Biến thể**:

- **Lưu lên Google Drive**: thay node Telegram bằng node **Google Drive → Upload**, nguồn là `data` (binary).
- **Đăng lên Discord webhook**: HTTP Request POST tới URL webhook Discord với field form-data `file` = `={{ $binary.data }}`.
- **Gửi ảnh qua email**: dùng node **Send Email** với file đính kèm từ `$binary.data`.

**Vòng lặp với nhiều prompt** (tạo ảnh hàng loạt): thêm node **Split In Batches** giữa Form và HTTP Request, đặt batch size là 1 — n8n sẽ tuần tự tạo từng ảnh theo prompt và gửi tất cả lên Telegram.

**Dùng tài khoản khác nhau cho mỗi request**: thêm node HTTP Request khác với `profile` và `project_id` khác trong body, hoặc để chatgpt2api xử lý round-robin bằng cách route qua `http://YOUR_SERVER_IP:3030/v1/images/generations` với `model:"flow/banana-2"` thay vì gọi trực tiếp captcha-solver.

### Dùng trực tiếp với curl

```bash
# JPEG nhị phân lưu thẳng ra file
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"<UUID>","prompt":"a samurai cat","return_binary":true}' \
     -o image.jpg
# header phản hồi chứa metadata: x-flow-model, x-flow-seed, x-flow-elapsed-ms

# JSON với CDN URL
curl -X POST http://YOUR_SERVER_IP:8010/v1/google/flow/generate-image \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"project_id":"<UUID>","prompt":"a samurai cat"}'
# → {"images":[{"url":"https://flow-content.google/image/...","seed":...}],"elapsed_ms":45000}
```

### Nhiều tài khoản Google

Mỗi tài khoản = một thư mục `profile`. Để thêm tài khoản thứ hai:

```bash
# 1) Mở phiên manual-login MỚI với tên profile MỚI
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"google-fx-2","url":"https://labs.google/fx/vi/tools/flow"}'

# 2) Mở noVNC → đăng nhập tài khoản Google thứ hai → mở một Flow project
#    → sao chép project_id từ URL

# 3) Thêm vào config.json:
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

Khởi động lại chatgpt2api. Provider sẽ **round-robin** giữa các tài khoản và đánh dấu "cooldown" một giờ cho tài khoản bị lỗi quota/429.

**Đồng thời**:
- Tài khoản khác nhau → song song (mỗi profile là một Chromium context độc lập)
- Cùng tài khoản → tuần tự (khóa profile ngăn hỏng cookie)

Một container xử lý tốt N tài khoản. Chỉ cần nhiều container nếu muốn mỗi tài khoản dùng IP outbound khác nhau (ví dụ: sau các proxy riêng biệt).

Liệt kê các profile đã tồn tại:

```bash
curl http://YOUR_SERVER_IP:8010/v1/session/list \
     -H "Authorization: Bearer $API_KEY"
```

## Tra cứu phạt nguội trên phatnguoi.vn (Turnstile)

```bash
# Tra cứu trực tiếp (dùng profile 'phatnguoi' theo mặc định)
curl -X POST http://YOUR_SERVER_IP:8010/v1/forms/phatnguoi \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"plate":"99A40201","vehicle_type":1}'
```

`vehicle_type`: 1 = ô tô, 2 = xe máy, 3 = xe điện.

MCP `vn_phat_nguoi` của vn-mcp-hub cũng dùng endpoint này khi biến môi trường `CAPTCHA_SOLVER_URL` được thiết lập — do đó mọi chat completion trong chatgpt2api gọi `check_traffic_violation` sẽ tự động fallback về đây khi API JSON trả về rỗng.

Turnstile của phatnguoi.vn khá nghiêm ngặt; cần đăng nhập qua noVNC một lần (quy trình tương tự Google Flow ở trên) dùng profile `phatnguoi`. Sau đó, cookie có hiệu lực từ vài giờ đến vài ngày.

## Luồng đăng nhập thủ công

Bất kỳ trang web nào chặn nội dung sau phiên người dùng thực đều có thể được khởi động một lần qua noVNC, sau đó điều khiển ở chế độ headless với profile đã lưu:

```bash
# 1) Mở trang web trong tab Chromium có giao diện hiển thị qua noVNC
curl -X POST http://YOUR_SERVER_IP:8010/v1/session/manual-login \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"ten-nao-do","url":"https://example.com/login"}'

# 2) Trỏ trình duyệt vào http://YOUR_SERVER_IP:6080/vnc.html
#    → đăng nhập / thực hiện các thao tác cần người dùng thực

# 3) Các lời gọi headless với cùng profile sẽ kế thừa cookie đã lưu
curl -X POST http://YOUR_SERVER_IP:8010/v1/browser/run \
     -H "Authorization: Bearer $API_KEY" \
     -H "Content-Type: application/json" \
     -d '{"profile":"ten-nao-do","url":"https://example.com/protected","wait_for":"main","script":"document.title"}'
```

## Biến môi trường

| Biến | Mặc định | Chức năng |
|---|---|---|
| `CAPTCHA_SOLVER_API_KEY` | `change-me` | Bearer token bắt buộc cho mọi lời gọi `/v1/*`. |
| `CAPTCHA_SOLVER_DATA_DIR` | `/data` | Nơi lưu các thư mục user-data-dir của profile. |
| `CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL` | (mặc định theo compose) | URL được trả về trong phản hồi `/v1/session/manual-login`. Dùng địa chỉ mà điện thoại/trình duyệt của bạn thực sự truy cập được. |
| `CAPTCHA_SOLVER_SOLVE_TIMEOUT` | `90` | Thời gian chờ tối đa cho mỗi lần giải (giây). |
| `CAPTCHA_SOLVER_2CAPTCHA_KEY` | _(không đặt)_ | Nếu được đặt, fallback về 2captcha khi tự giải Turnstile thất bại. |

## Xử lý sự cố

**`Could not capture ya29 token. Profile likely not logged in.`**
Profile Google không có cookie phiên. Chạy lại `/v1/session/manual-login` với đúng tên profile và đăng nhập qua noVNC.

**`Flow UI never hydrated (timeout).`**
Google đã đăng xuất profile (~một lần mỗi vài tháng với gói miễn phí). Chạy lại manual login.

**`Did not observe flowMedia POST within timeout.`**
Giao diện Flow đã thay đổi (nút di chuyển, ô nhập prompt trở thành element khác). Mở noVNC và xem điều gì thực sự xảy ra khi bạn bấm "Tạo" thủ công. Cập nhật selector trong `src/solvers/flow_google.py` nếu cần.

**`turnstile solve timed out` (đặc biệt trên phatnguoi.vn)**
Cloudflare Turnstile từ chối render widget với IP của server. Đây là hiện tượng bình thường với IP datacenter. Cách khắc phục:
1. Tick captcha thủ công một lần qua noVNC — cookie có hiệu lực vài giờ
2. Đặt `CAPTCHA_SOLVER_2CAPTCHA_KEY` để dùng dịch vụ trả phí làm dự phòng
3. Chạy container sau một proxy dân dụng (residential proxy)

**`Connection refused` từ chatgpt2api → captcha-solver**
Container chatgpt2api không thể kết nối tới `localhost:8010` (đó là localhost của chính nó). Dùng IP host (`http://YOUR_SERVER_IP:8010`) hoặc đặt cả hai container trong cùng Docker network và dùng tên container (`http://captcha-solver:8010`).
