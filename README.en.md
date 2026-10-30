[中文](README.md) · [English](README.en.md) · [Tiếng Việt](README.vi.md)

<h1 align="center">ChatGPT2API</h1>


<p align="center">ChatGPT2API mainly reverse-engineers and wraps ChatGPT's official website capabilities, providing an OpenAI-compatible image API / proxy for ChatGPT image generation, image editing, and multi-image composite editing scenarios, and integrates an online drawing board, account pool management, multiple account import methods, and Docker self-hosted deployment.</p>

> [!WARNING]
> Disclaimer:
>
> This project involves reverse-engineering research on ChatGPT's official text generation, image generation, and image editing interfaces, for personal learning, technical research, and non-commercial technical exchange only.
>
> - This project must not be used for any commercial purpose, profit-making use, bulk operations, automated abuse, or large-scale calls.
> - This project must not be used to disrupt market order, engage in malicious competition, arbitrage or resale of related services, or any act that violates OpenAI's terms of service or local laws and regulations.
> - This project must not be used to generate, spread, or assist in generating illegal, violent, pornographic, or minor-related content, or for fraud, scams, harassment, or other illegal or improper purposes.
> - Users bear all risks themselves, including but not limited to account restriction, temporary suspension, or permanent ban, as well as legal liability arising from improper use.
> - Using this project means you have fully understood and agreed to this entire disclaimer; any consequences arising from misuse, violation, or illegal use are borne solely by the user.
> - This project is implemented based on reverse-engineering research of ChatGPT's official website capabilities, and carries the risk of account restriction, temporary suspension, or permanent ban. Do not use your own important, frequently used, or high-value accounts for testing.


## Sponsors

<table>
  <tr>
    <td width="190" align="center">
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api"><img src="assets/atlascloud.svg" width="163" alt="Atlas Cloud"></a>
    </td>
    <td>
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api">Atlas Cloud</a> is a full-modal AI inference platform that gives developers a single AI API to access video generation, image generation, and LLM APIs. Instead of managing multiple vendor integrations, you connect once and get unified access to 300+ curated models across all modalities. Check out <a href="https://www.atlascloud.ai/console/coding-plan">Atlas Cloud's new coding plan promotion</a> for more budget-friendly API access.
    </td>
  </tr>
</table>

## Quick Start

### Run with Docker

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
docker compose up -d
```

Before starting, set `auth-key` in `config.json`, or override it via `CHATGPT2API_AUTH_KEY` in `docker-compose.yml`.

- Web panel: `http://localhost:3000`
- API address: `http://localhost:3000/v1`
- Data directory: `./data`

### WARP / FlareSolverr Stable Proxy Deployment

If your image pipeline frequently runs into Cloudflare blocks, you can enable the bundled WARP + Privoxy + FlareSolverr setup:

```bash
cp .env.example .env
docker compose -f docker-compose.warp.yml up -d --build
```

This compose file starts:

- `warp-proxy`: provides a WARP SOCKS5 exit.
- `privoxy`: converts the WARP SOCKS5 proxy into an HTTP proxy.
- `flaresolverr`: refreshes the Cloudflare clearance.
- `init-config`: idempotently writes the default `proxy_runtime` config.
- `app`: starts the ChatGPT2API main service.

By default, only upstream OpenAI / ChatGPT requests go through the stable proxy; auxiliary paths such as account email and CPA are not forced through it. The account's own configured proxy has the highest priority, followed by the stable proxy runtime, then the explicit proxy, and finally the legacy global proxy.

You can adjust the port and proxy runtime parameters in `.env`, or manually save, test the proxy, and test the clearance from the "Stable Proxy Runtime" panel on the settings page.

### Local Development

Start the backend:

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
uv sync
uv run main.py
```

Start the frontend:

```bash
cd chatgpt2api/web
bun install
bun run dev
```

Upgrading to a new version later:

```bash
docker pull ghcr.io/basketikun/chatgpt2api:latest
docker-compose down
docker-compose up -d

```

### Storage Backend Configuration

Switch storage backends via the `STORAGE_BACKEND` environment variable:

- `json` - local JSON file (default)
- `sqlite` - local SQLite database
- `postgres` - external PostgreSQL (requires `DATABASE_URL`)
- `git` - private Git repository (requires `GIT_REPO_URL` and `GIT_TOKEN`)

Example: using PostgreSQL

```yaml
environment:
  - STORAGE_BACKEND=postgres
  - DATABASE_URL=postgresql://user:password@host:5432/dbname
```

## Features

### API Compatibility

- Compatible with the `POST /v1/images/generations` image generation endpoint
- Compatible with the `POST /v1/images/edits` image editing endpoint
- Compatible with the `POST /v1/chat/completions` endpoint for image scenarios
- Compatible with the `POST /v1/responses` endpoint for image scenarios
- `GET /v1/models` returns `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`,
  `gpt-5-mini`
- Supports returning multiple generation results via `n`
- Supports generating editable PPT files
- Supports generating editable PSD files
- Supports reverse-engineered access to Codex's drawing endpoint, available only to `Plus` / `Team` / `Pro` subscriptions, with the model alias `codex-gpt-image-2`; you can map it back to
  `gpt-image-2` yourself in other scenarios to distinguish it from the official website's drawing, which also means the same account gets separate image generation quotas for the official website and Codex

### Online Drawing Board

- Built-in online drawing workbench, supporting generation, image editing, and multi-image composite editing
- Supports model selection among `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`, `gpt-5-mini`
- Edit mode supports reference image upload
- Frontend supports multi-image generation interaction
- Saves image session history locally, supporting review, deletion, and clearing
- Supports server-side caching of image URLs
- Image generation progress tracking, can keep waiting after a timeout
- Image lazy loading and scroll position memory, optimizing performance for scenarios with many images

### Account Pool Management

- Automatically refreshes account email, type, quota, and recovery time (with asynchronous progress tracking)
- Polls available accounts to perform image generation and image editing
- Automatically removes invalid tokens when a token-invalid error is encountered
- Periodically checks rate-limited accounts and refreshes them automatically
- Supports password re-login to recover abnormal accounts, with automatic re-login after refresh
- Supports configuring a global HTTP / HTTPS / SOCKS5 / SOCKS5H proxy from the web page
- Supports the WARP / FlareSolverr stable proxy runtime
- Supports search, filter, batch refresh, export, manual editing, and cleanup of accounts
- Supports four import methods: local CPA JSON file import, remote CPA server import, `sub2api` server import, `access_token` import
- Supports configuring a `sub2api` server on the settings page, filtering and batch-importing OpenAI OAuth accounts from it

### Experimental / Planned

- See detailed status here: [Feature List](./docs/feature-status.en.md)

## Screenshots

<table width="100%">
  <tr>
    <td width="50%"><img src="https://i.ibb.co/Jj8nfwwP/image.png" alt="image" border="0"></td>
    <td width="50%"><img src="https://i.ibb.co/pqf235v/image-edit.png" alt="image edit" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="https://i.ibb.co/tPcqtVfd/chery-studio.png" alt="chery studio" border="0"></td>
    <td width="50%"><img src="https://i.ibb.co/PsT9YHBV/account-pool.png" alt="account pool" border="0"></td>
  </tr>
  <tr>
    <td width="50%"><img src="https://i.ibb.co/rRWLG08q/new-api.png" alt="new api" border="0"></td>
  </tr>
</table>

## API

All AI endpoints require this request header:

```http
Authorization: Bearer <auth-key>
```

<details>
<summary><code>GET /v1/models</code></summary>
<br>

Returns the list of currently exposed image models.

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <auth-key>"
```

<details>
<summary>Details</summary>
<br>

| Field | Description |
|:-----|:-----------------------------------------------------------------------------------------------------------|
| Returned models | `gpt-image-2`, `codex-gpt-image-2`, `auto`, `gpt-5`, `gpt-5-1`, `gpt-5-2`, `gpt-5-3`, `gpt-5-3-mini`, `gpt-5-mini` |
| Integration scenarios | Can be integrated into upstreams or clients such as Cherry Studio, New API |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/generations</code></summary>
<br>

OpenAI-compatible image generation endpoint, for text-to-image.

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "一只漂浮在太空里的猫",
    "n": 1,
    "response_format": "b64_json"
  }'
```

<details>
<summary>Field descriptions</summary>
<br>

| Field | Description |
|:------------------|:---------------------------------------------------|
| `model` | Image model; current valid values follow the `/v1/models` response, `gpt-image-2` is recommended |
| `prompt` | Image generation prompt |
| `n` | Number to generate; currently limited by the backend to `1-4` |
| `response_format` | Currently included in the request model, defaulting to `b64_json` |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/edits</code></summary>
<br>

OpenAI-compatible image editing endpoint; you can upload an image file, or pass an image link in the official JSON format to generate an edited result.

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -F "model=gpt-image-2" \
  -F "prompt=把这张图改成赛博朋克夜景风格" \
  -F "n=1" \
  -F "image=@./input.png"
```

You can also pass an image URL directly:

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <auth-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2",
    "prompt": "把这张图改成赛博朋克夜景风格",
    "images": [
      {"image_url": "https://example.com/input.png"}
    ]
  }'
```

<details>
<summary>Field descriptions</summary>
<br>

| Field | Description |
|:------------|:----------------------------------------------|
| `model` | Image model, `gpt-image-2` |
| `prompt` | Image editing prompt |
| `n` | Number to generate; currently limited by the backend to `1-4` |
| `image` | The image file to edit, uploaded via multipart/form-data |
| `images` | JSON array of image references, supports `{"image_url": "https://..."}` |
| `image_url` | In form mode, an image link can also be passed directly; the field can be repeated for multiple images |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/chat/completions</code></summary>
<br>

A Chat Completions-compatible endpoint for text, web search, and image scenarios; it is not a full general-purpose chat proxy.

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-image-2",
    "messages": [
      {
        "role": "user",
        "content": "生成一张雨夜东京街头的赛博朋克猫"
      }
    ],
    "n": 1
  }'
```

<details>
<summary>Field descriptions</summary>
<br>

| Field | Description |
|:---------------------|:-----------------------------------------------------------------------------|
| `model` | Text, search, or image model; a search model triggers web search compatibility logic |
| `messages` | Message array, supports text, search, and image request content |
| `n` | Image generation count; parsed under the current implementation as the number of images |
| `stream` | Supported in text, search, and image scenarios; still being tested |
| `tools` | Text scenarios support `web_search` / `web_search_preview` / `web_search_preview_2025_03_11` |
| `web_search_options` | When passed, triggers web search compatibility logic |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/responses</code></summary>
<br>

A Responses API-compatible endpoint for text, web search, and image generation tool calls; it is not a full general-purpose Responses API proxy.

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <auth-key>" \
  -d '{
    "model": "gpt-5",
    "input": "生成一张未来感城市天际线图片",
    "tools": [
      {
        "type": "image_generation"
      }
    ]
  }'
```

<details>
<summary>Field descriptions</summary>
<br>

| Field | Description |
|:---------|:----------------------------------------------------------------------------------------|
| `model` | The response echoes back this model field; search and image generation follow their respective compatibility logic |
| `input` | Input content; search uses the last user text message, image generation needs a prompt it can parse out |
| `tools` | Supports `image_generation`, `web_search`, `web_search_preview`, `web_search_preview_2025_03_11` |
| `stream` | Implemented, but still being tested |

<br>
</details>
</details>

## Community Support

Learn AI on LinuxDO: [LinuxDO](https://linux.do)

## Contributors

Thanks to all the developers who have contributed to this project:

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=basketikun/chatgpt2api&type=date&legend=top-left)](https://www.star-history.com/?repos=basketikun%2Fchatgpt2api&type=date&legend=top-left)
