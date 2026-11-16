<h1 align="center">ChatGPT2API</h1>


<p align="center">ChatGPT2API 主要是对 ChatGPT 官网相关能力进行逆向整理与封装，提供面向 ChatGPT 图片生成、图片编辑、多图组图编辑场景的 OpenAI 兼容图片 API / 代理，并集成在线画图、号池管理、多种账号导入方式与 Docker 自托管部署能力。基于 Go 开发，支持高并发，内存占用极低，空闲时仅约 25MB。</p>

> [!WARNING]
> 免责声明：
>
> 本项目涉及对 ChatGPT 官网文本生成、图片生成与图片编辑等相关接口的逆向研究，仅供个人学习、技术研究与非商业性技术交流使用。
>
> - 严禁将本项目用于任何商业用途、盈利性使用、批量操作、自动化滥用或规模化调用。
> - 严禁将本项目用于破坏市场秩序、恶意竞争、套利倒卖、二次售卖相关服务，以及任何违反 OpenAI 服务条款或当地法律法规的行为。
> - 严禁将本项目用于生成、传播或协助生成违法、暴力、色情、未成年人相关内容，或用于诈骗、欺诈、骚扰等非法或不当用途。
> - 使用者应自行承担全部风险，包括但不限于账号被限制、临时封禁或永久封禁以及因违规使用等所导致的法律责任。
> - 使用本项目即视为你已充分理解并同意本免责声明全部内容；如因滥用、违规或违法使用造成任何后果，均由使用者自行承担。
> - 本项目基于对 ChatGPT 官网相关能力的逆向研究实现，存在账号受限、临时封禁或永久封禁的风险。请勿使用你自己的重要账号、常用账号或高价值账号进行测试。


## 赞助商

<table>
  <tr>
    <td width="190" align="center">
      <a href="https://kunrouai.com/?utm_source=chatgpt2api"><img src="assets/kunrouai.svg" width="163" alt="坤肉AI"></a>
    </td>
    <td>
      <a href="https://kunrouai.com/?utm_source=chatgpt2api">坤肉AI</a> 是一站式 AI 视觉创作平台，集 AI 生图、视频生成、多人协作画布及 Agent/MCP 连接于一体，适合个人创作与团队协作，同时面向企业提供源码出售及私有化部署服务，欢迎企业咨询合作！另有 <a href="https://api.kunrouai.com/?utm_source=chatgpt2api">API 开放平台</a>，提供丰富的 AI 模型 API 接口，支持快速接入与集成，欢迎开发者及企业对接合作！
    </td>
  </tr>
  <tr>
    <td width="190" align="center">
      <a href="https://88api.ai/sign-up?aff=py0a"><img src="assets/88api.png" width="163" alt="88API"></a>
    </td>
    <td>
      <a href="https://88api.ai/sign-up?aff=py0a">88API</a> 是一家由香港企业运营、主要面向开发者、创作者与 AI 应用用户的一站式多模型 API 平台，通过统一接口接入文本、图片、语音和视频模型，覆盖 AI 编程、智能翻译、内容创作、配音、图像生成、视频生成等常见工作流。支持在常用客户端中完成 Provider 添加并切换，支持国际主流付款方式，可提供发票，提供企业级稳定服务。通过 <a href="https://88api.ai/sign-up?aff=py0a">此链接注册</a> 可以获取专属赠送额度！
    </td>
  </tr>
  <tr>
    <td width="190" align="center">
      <a href="https://www.ipwo.net/?ref=githubbasketikunchatgpt2api"><img src="assets/ipwo.png" width="163" alt="IPWO"></a>
    </td>
    <td>
      <a href="https://www.ipwo.net/?ref=githubbasketikunchatgpt2api">IPWO</a> 住宅代理提供动态、静态及不限量住宅代理，覆盖 195+ 个国家和地区，支持 HTTP(S) 与 SOCKS5 协议。<br>对于使用 ChatGPT2API 进行 AI 图片生成、图片编辑和 API 集成的开发者，IPWO 支持免费测试，支持地区选择与网络连接配置，满足多种开发和测试需求。优惠折扣码：<b>0200</b>。
    </td>
  </tr>
  <tr>
    <td width="190" align="center">
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api"><img src="assets/atlascloud.svg" width="163" alt="Atlas Cloud"></a>
    </td>
    <td>
      <a href="https://www.atlascloud.ai/zh?utm_source=github&utm_medium=link&utm_campaign=chatgpt2api">Atlas Cloud</a> is a full-modal AI inference platform that gives developers a single AI API to access video generation, image generation, and LLM APIs. Instead of managing multiple vendor integrations, you connect once and get unified access to 300+ curated models across all modalities. Check out <a href="https://www.atlascloud.ai/console/coding-plan">Atlas Cloud's new coding plan promotion</a> for more budget-friendly API access.
    </td>
  </tr>
</table>

## 快速开始

### Docker 运行

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
docker compose up -d
```

启动前请先在 `config.yaml` 中设置 `api-key`，也可以在 `.env` 中通过 `CHATGPT2API_AUTH_KEY` 覆盖。

- Web 面板：`http://localhost:3000`
- API 地址：`http://localhost:3000/v1`
- 数据目录：`./data`

### 本地开发

```bash
go run .
```

前端位于 `web/`，无需构建，服务启动后直接访问。

部署与升级见 [docs/deployment.md](docs/deployment.md)。

## 功能

### API 兼容能力

- 兼容 `POST /v1/images/generations` 图片生成接口
- 兼容 `POST /v1/images/edits` 图片编辑接口
- 兼容 `POST /v1/audio/speech` 语音合成接口（ChatGPT 官网 voice 模型）
- 兼容 `POST /v1/audio/transcriptions` 语音转写接口
- 兼容面向图片场景的 `POST /v1/chat/completions`
- 兼容面向图片场景的 `POST /v1/responses`
- `GET /v1/models` 汇总各账号可用的官方模型，常见值包括 `auto`、`gpt-6`、`gpt-6-mini`、`gpt-6-t-mini`、
  `gpt-5-6`、`gpt-5-6-mini`、`gpt-5.6-terra-wm`、`gpt-5.6-luna-wm`、`research`，以及生图别名 `gpt-image-2.6`
- 支持通过 `n` 返回多张生成结果
- 支持 Codex 中的画图接口逆向，仅 `Plus` / `Team` / `Pro` 订阅可用；对外仍统一使用 `gpt-image-2.6`，在用户密钥上选择订阅等级和线路（Web / Codex）决定走哪类账号，
  同一账号会同时有官网和 Codex 两份生图额度；Codex 线路默认主控模型 `gpt-6-luna`、画图工具模型 `gpt-image-2.6`，可在设置页调整

### 创作台

- 内置创作台，支持对话（联网搜索、图片提问）、生图与图片编辑、语音合成与转写
- 生图支持质量、尺寸、数量和参考图设置，任务可在后台继续并支持超时后继续等待
- 创作记录保存在服务端，可回看、删除和清空
- 非管理员密钥登录后直接进入创作台

### 号池管理功能

- 自动刷新账号邮箱、类型、额度和恢复时间（异步进度追踪）
- 轮询可用账号执行图片生成与图片编辑
- 遇到 Token 失效类错误时自动剔除无效 Token
- 定时检查限流账号并自动刷新
- 支持密码重新登录恢复异常账号，刷新后可自动重登
- 支持网页端配置全局 HTTP / HTTPS / SOCKS5 / SOCKS5H 代理
- 支持 WARP / FlareSolverr 稳定代理运行时
- 支持搜索、筛选、批量刷新、导出、手动编辑和清理账号
- 支持四种导入方式：本地 CPA JSON 文件导入、远程 CPA 服务器导入、`sub2api` 服务器导入、`access_token` 导入
- 支持在设置页配置 `sub2api` 服务器，筛选并批量导入其中的 OpenAI OAuth 账号

## 效果展示

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

所有 AI 接口都需要请求头：

```http
Authorization: Bearer <api-key>
```

<details>
<summary><code>GET /v1/models</code></summary>
<br>

返回当前暴露的图片模型列表。

```bash
curl http://localhost:8000/v1/models \
  -H "Authorization: Bearer <api-key>"
```

<details>
<summary>说明</summary>
<br>

| 字段   | 说明                                                                                                         |
|:-----|:-----------------------------------------------------------------------------------------------------------|
| 返回模型 | 以 `/v1/models` 实时返回为准，常见 `auto`、`gpt-6`、`gpt-6-mini`、`gpt-5-6`、`gpt-5-6-mini`、`gpt-5.6-terra-wm`、`gpt-5.6-luna-wm`、`research`、`gpt-image-2.6` |
| 接入场景 | 可接入 Cherry Studio、New API 等上游或客户端                                                                          |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/generations</code></summary>
<br>

OpenAI 兼容图片生成接口，用于文生图。

```bash
curl http://localhost:8000/v1/images/generations \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "model": "gpt-image-2.6",
    "prompt": "一只漂浮在太空里的猫",
    "n": 1,
    "response_format": "b64_json"
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段                | 说明                                                 |
|:------------------|:---------------------------------------------------|
| `model`           | 图片模型，当前可用值以 `/v1/models` 返回结果为准，推荐使用 `gpt-image-2.6` |
| `prompt`          | 图片生成提示词                                            |
| `n`               | 生成数量，当前后端限制为 `1-4`                                 |
| `size`            | 可选，如 `1024x1024`、`1536x1024`；会换算成上游的 `aspect_ratio` |
| `quality`         | 可选，`auto` / `low` / `medium` / `high` 等，作为质量提示传给模型       |
| `response_format` | 当前请求模型中包含该字段，默认值为 `b64_json`                       |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/images/edits</code></summary>
<br>

OpenAI 兼容图片编辑接口，可上传图片文件，也可按官方 JSON 格式传入图片链接并生成编辑结果。

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <api-key>" \
  -F "model=gpt-image-2.6" \
  -F "prompt=把这张图改成赛博朋克夜景风格" \
  -F "n=1" \
  -F "image=@./input.png"
```

也可以直接传图片 URL：

```bash
curl http://localhost:8000/v1/images/edits \
  -H "Authorization: Bearer <api-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gpt-image-2.6",
    "prompt": "把这张图改成赛博朋克夜景风格",
    "images": [
      {"image_url": "https://example.com/input.png"}
    ]
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段          | 说明                                            |
|:------------|:----------------------------------------------|
| `model`     | 图片模型， `gpt-image-2.6`                           |
| `prompt`    | 图片编辑提示词                                       |
| `n`         | 生成数量，当前后端限制为 `1-4`                            |
| `image`     | 需要编辑的图片文件，使用 multipart/form-data 上传           |
| `images`    | JSON 图片引用数组，支持 `{"image_url": "https://..."}` |
| `image_url` | 表单模式下也可直接传图片链接，支持重复字段传多张图                     |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/chat/completions</code></summary>
<br>

面向文本、网页搜索与图片场景的 Chat Completions 兼容接口，不是完整通用聊天代理。

```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "model": "gpt-image-2.6",
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
<summary>字段说明</summary>
<br>

| 字段                   | 说明                                                                           |
|:---------------------|:-----------------------------------------------------------------------------|
| `model`              | 文本、搜索或图片模型；搜索模型会触发网页搜索兼容逻辑                                                   |
| `messages`           | 消息数组，支持文本、搜索和图片请求内容                                                          |
| `n`                  | 图片生成数量，按当前实现解析为图片数量                                                          |
| `stream`             | 文本、搜索和图片场景均支持，仍在测试                                                           |
| `tools`              | 文本场景支持 `web_search` / `web_search_preview` / `web_search_preview_2025_03_11` |
| `web_search_options` | 传入时会触发网页搜索兼容逻辑                                                               |
| `thinking_effort`    | 可选，按账号/模型透传 `low` / `medium` / `high` / `standard` / `extended` / `xhigh` / `max` / `ultra` 等档位；`auto` 表示不发送。不同套餐开放的档位不同 |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/responses</code></summary>
<br>

面向文本、网页搜索和图片生成工具调用的 Responses API 兼容接口，不是完整通用 Responses API 代理。

```bash
curl http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "model": "gpt-6",
    "input": "生成一张未来感城市天际线图片",
    "tools": [
      {
        "type": "image_generation"
      }
    ]
  }'
```

<details>
<summary>字段说明</summary>
<br>

| 字段       | 说明                                                                                      |
|:---------|:----------------------------------------------------------------------------------------|
| `model`  | 响应中会回显该模型字段，搜索和图片生成会走对应兼容逻辑                                                             |
| `input`  | 输入内容；搜索使用最后一条用户文本，图片生成需能解析出提示词                                                          |
| `tools`  | 支持 `image_generation`、`web_search`、`web_search_preview`、`web_search_preview_2025_03_11` |
| `stream` | 已实现，但仍在测试                                                                               |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/audio/speech</code></summary>
<br>

调用 ChatGPT 官网 voice 模型做语音合成，返回音频二进制。需要 `Plus` / `Team` / `Pro` 等带语音能力的登录态账号。

```bash
curl http://localhost:8000/v1/audio/speech \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{
    "model": "gpt-tts",
    "input": "你好，这是一段语音合成的测试。",
    "voice": "alloy",
    "response_format": "mp3"
  }' \
  --output speech.mp3
```

<details>
<summary>字段说明</summary>
<br>

| 字段                | 说明                                                                                                                     |
|:------------------|:-----------------------------------------------------------------------------------------------------------------------|
| `input`           | 要合成的文本，必填                                                                                                              |
| `voice`           | 官网音色标识（`juniper`、`maple`、`cove`、`breeze`、`orbit`/Spruce、`glimmer`/Sol、`ember`、`fathom`/Arbor、`vale`）；也兼容 OpenAI 音色名（`alloy`、`ash`、`coral`、`echo`、`fable`、`onyx`、`nova`、`sage`、`shimmer`） |
| `response_format` | 音频格式，默认 `mp3`                                                                                                           |
| `email`           | 可选，指定使用号池中的某个账号                                                                                                        |

<br>
</details>
</details>

<details>
<summary><code>POST /v1/audio/transcriptions</code></summary>
<br>

调用 ChatGPT 官网语音识别接口做转写，`multipart/form-data` 上传音频文件。

```bash
curl http://localhost:8000/v1/audio/transcriptions \
  -H "Authorization: Bearer <api-key>" \
  -F "file=@speech.mp3" \
  -F "model=gpt-transcribe"
```

<details>
<summary>说明</summary>
<br>

| 字段                | 说明                                       |
|:------------------|:-----------------------------------------|
| `file`            | 音频文件，必填                                  |
| `response_format` | 传 `text` 时返回纯文本，默认返回 `{"text": "..."}`     |
| `email`           | 可选，指定使用号池中的某个账号                          |

<br>
</details>
</details>

## 社区支持

学 AI , 上 L 站：[LinuxDO](https://linux.do)

## Contributors

感谢所有为本项目做出贡献的开发者：

<a href="https://github.com/basketikun/chatgpt2api/graphs/contributors">
  <img alt="Contributors" src="https://contrib.rocks/image?repo=basketikun/chatgpt2api" />
</a>

## Star History

[![Star History Chart](https://api.star-history.com/chart?repos=basketikun/chatgpt2api&type=date&legend=top-left)](https://www.star-history.com/?repos=basketikun%2Fchatgpt2api&type=date&legend=top-left)

