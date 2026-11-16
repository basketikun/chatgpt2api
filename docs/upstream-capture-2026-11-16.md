# 2026-11-16 ChatGPT 网页端真实抓包记录

本文记录一次真实 Chrome 会话下的 ChatGPT 网页端请求，用于后续排查上游协议变化。只保留核心请求/响应结构与指纹头，`Authorization`、Cookie、sentinel token、`conduit_token`、account id、邮箱等敏感值全部打码或替换为占位符。

## 环境

| 项 | 值 |
|:--|:--|
| 抓包时间 | 2026-11-16 10:45（Asia/Shanghai） |
| 浏览器 | Chrome 157.0.8103.51（Windows 11 x64） |
| 页面 | `https://chatgpt.com/`、`https://chatgpt.com/images` |
| 页面 `data-build` | `5750d92c02e7d1b6aa2ea1ffdb1c1fb376272952` |
| 账号套餐 | free |
| 抓包方式 | 独立 Chrome profile + CDP `Network.requestWillBeSent`，真实点击/输入触发 |
| 默认模型 | 请求 `model: "auto"`，响应 `model_slug: "gpt-6-t-mini"` |

## 核心请求头

文本会话与生图请求共同携带：

```http
authorization: Bearer <redacted>
chatgpt-account-id: <redacted-account-uuid>
oai-did: <device-uuid>
oai-device-id: <device-uuid>
oai-language: zh-CN
originator: Codex Browser
x-openai-web-frontend: codex_webview
x-openai-codex-window-type: browser
x-openai-rate-limit-join-workspace: 1
x-openai-rejoin-pro-cta: 1
x-oai-mcp-form-version: 2
x-oai-turn-trace-id: <turn-trace-uuid>
content-type: application/json
origin: https://chatgpt.com
referer: https://chatgpt.com/
sec-ch-ua: "Not-A.Brand";v="99", "Google Chrome";v="157", "Chromium";v="157"
sec-ch-ua-mobile: ?0
sec-ch-ua-platform: "Windows"
user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/157.0.0.0 Safari/537.36
```

正式 `/f/conversation` 额外携带：

```http
x-conduit-token: <redacted>
openai-sentinel-chat-requirements-token: <redacted>
openai-sentinel-proof-token: <redacted>
openai-sentinel-turnstile-token: <redacted>
x-openai-web-sse-compression: gzip
```

说明：

- `x-openai-web-sse-compression: gzip` 是网页端实验开关，反代实现可以不带，按未压缩 SSE 读取即可。
- `x-openai-genui-client-actions`、`x-openai-beacon-*`、`oai-echo-logs` 属于前端遥测/组件能力，不影响对话主链路。
- 网页端同时发 `oai-did` 与 `oai-device-id`，值一致。

## 文本会话

### 1. `POST /backend-api/f/conversation/prepare`

准备请求是精简载荷，不带 `messages`、`partial_query`：

```json
{
  "client_prepare_state": "sent",
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "local_function_names": ["local.continue_in_work"],
  "client_prepare_dispatch": "debounced",
  "client_prepare_source": "composer_editor_state"
}
```

响应核心字段：

```json
{
  "status": "ok",
  "conduit_token": "<redacted-jwt>"
}
```

### 2. `POST /backend-api/f/conversation`

```json
{
  "turn_attribution": { "turn_trigger": "composer" },
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "client_contextual_info": {
    "app_name": "chatgpt.com",
    "app_surface": "codex_browser",
    "has_web_push_capabilities": true,
    "web_push_notification_permission": "default"
  },
  "local_function_names": ["local.continue_in_work"],
  "messages": [
    {
      "author": { "metadata": {}, "name": null, "role": "user" },
      "channel": null,
      "content": { "content_type": "text", "parts": ["只回复两个字：收到"] },
      "create_time": 1794797126.795,
      "end_turn": null,
      "id": "88cc7961-6275-420b-9356-696c60b60480",
      "metadata": {
        "automation_creation_attribution": {
          "origin": "conversation",
          "flow_id": "88cc7961-6275-420b-9356-696c60b60480"
        }
      },
      "recipient": "all",
      "status": "finished_successfully",
      "update_time": null,
      "weight": 1
    }
  ],
  "supported_encodings": ["v1"],
  "genui_state_snapshots": [],
  "client_prepare_state": "success"
}
```

关键点：

- 普通文本对话**没有** `conversation_mode`，**没有** 空 `system_hints`。
- `turn_attribution` 与 `genui_state_snapshots` **仍然存在**，不要删除。
- `author.name` 为 `null`，`author.metadata` 为空对象。
- `metadata.automation_creation_attribution.flow_id` 与消息 `id` 相同。
- `messages` 只放本轮用户消息；新会话 `parent_message_id` 为 `client-created-root`。

### 3. `GET /backend-api/conversations/{id}?num_turns=10&include_has_versions=true`

真实网页端读取会话详情使用**复数**接口，返回 `messages` 数组：

```json
{
  "conversation_id": "<conversation-id>",
  "default_model_slug": "auto",
  "current_node": "<assistant-message-id>",
  "messages": [
    {
      "id": "<system-message-id>",
      "author": { "role": "system", "name": null, "metadata": {} },
      "content": { "content_type": "text", "parts": [""] },
      "status": "finished_successfully",
      "metadata": {
        "system_hints": ["reason"],
        "is_visually_hidden_from_conversation": true
      },
      "recipient": "all",
      "channel": null
    },
    {
      "id": "<user-message-id>",
      "author": { "role": "user", "name": null, "metadata": {} },
      "content": { "content_type": "text", "parts": ["只回复两个字：收到"] },
      "status": "finished_successfully",
      "weight": 1.0,
      "recipient": "all",
      "channel": null
    },
    {
      "id": "<assistant-message-id>",
      "author": { "role": "assistant", "name": null, "metadata": {} },
      "content": { "content_type": "text", "parts": ["收到"] },
      "status": "finished_successfully",
      "end_turn": true,
      "weight": 1.0,
      "metadata": {
        "finish_details": { "type": "stop", "stop_tokens": [200002] },
        "is_complete": true,
        "model_slug": "gpt-6-t-mini",
        "default_model_slug": "auto"
      },
      "recipient": "all",
      "channel": "final"
    }
  ],
  "page_info": {
    "start_cursor": "<system-message-id>",
    "end_cursor": "<assistant-message-id>",
    "has_previous_page": false,
    "has_next_page": false
  }
}
```

## 生图会话

### 1. `POST /backend-api/f/conversation/prepare`

比文本多一个 `system_hints`：

```json
{
  "client_prepare_state": "sent",
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "system_hints": ["picture_v2"],
  "local_function_names": ["local.continue_in_work"],
  "client_prepare_dispatch": "debounced",
  "client_prepare_source": "composer_editor_state"
}
```

### 2. `POST /backend-api/f/conversation`

```json
{
  "turn_attribution": { "turn_trigger": "composer" },
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "system_hints": ["picture_v2"],
  "client_contextual_info": {
    "app_name": "chatgpt.com",
    "app_surface": "codex_browser",
    "has_web_push_capabilities": true,
    "web_push_notification_permission": "default"
  },
  "local_function_names": ["local.continue_in_work"],
  "messages": [
    {
      "author": { "metadata": {}, "name": null, "role": "user" },
      "channel": null,
      "content": {
        "content_type": "text",
        "parts": ["一个红色圆形图标，白色背景，极简风格"]
      },
      "create_time": 1794797173.206,
      "end_turn": null,
      "id": "66811a82-3d46-4c51-95c7-8596720896b7",
      "metadata": {
        "automation_creation_attribution": {
          "origin": "conversation",
          "flow_id": "66811a82-3d46-4c51-95c7-8596720896b7"
        },
        "system_hints": ["picture_v2"]
      },
      "recipient": "all",
      "status": "finished_successfully",
      "update_time": null,
      "weight": 1
    }
  ],
  "supported_encodings": ["v1"],
  "genui_state_snapshots": [],
  "client_prepare_state": "success"
}
```

关键点：

- 生图的 `system_hints: ["picture_v2"]` 同时出现在**顶层**和**用户消息 metadata**。
- 没选尺寸/数量时，请求里**没有** `image_generation_settings`；选了宽高比/数量后才写进用户消息 metadata。
- 图片生成结果不是独立接口，而是本会话后续的 `role=tool` 消息。

### 3. `POST /backend-api/conversation/init`

生图页会额外调用 init，`system_hints` 为 `["picture_v2"]`：

```json
{
  "conversation_id": null,
  "conversation_origin": null,
  "gizmo_id": null,
  "requested_default_model": null,
  "system_hints": ["picture_v2"],
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480
}
```

普通文本的 init 把 `system_hints` 设为 `null`：

```json
{
  "conversation_id": null,
  "conversation_origin": null,
  "gizmo_id": null,
  "requested_default_model": null,
  "system_hints": null,
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480
}
```

## 图生图 / 图片编辑

### 1. `POST /backend-api/f/conversation/prepare`

带图的 prepare 额外传附件 MIME 与已上传文件 ID：

```json
{
  "attachment_mime_types": ["image/png"],
  "prepare_image_upload_ids": ["file_<upload-id-1>", "file_<upload-id-2>"],
  "client_prepare_state": "sent",
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "system_hints": ["picture_v2"],
  "local_function_names": ["local.continue_in_work"],
  "client_prepare_dispatch": "debounced",
  "client_prepare_source": "composer_editor_state"
}
```

### 2. `POST /backend-api/f/conversation`

带图消息是 `multimodal_text`，**图片指针在前、文本在最后**：

```json
{
  "turn_attribution": { "turn_trigger": "composer" },
  "action": "next",
  "model": "auto",
  "parent_message_id": "client-created-root",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "system_hints": ["picture_v2"],
  "client_contextual_info": {
    "app_name": "chatgpt.com",
    "app_surface": "codex_browser",
    "has_web_push_capabilities": true,
    "web_push_notification_permission": "default"
  },
  "local_function_names": ["local.continue_in_work"],
  "messages": [
    {
      "author": { "metadata": {}, "name": null, "role": "user" },
      "channel": null,
      "content": {
        "content_type": "multimodal_text",
        "parts": [
          {
            "asset_pointer": "sediment://file_<upload-id>",
            "content_type": "image_asset_pointer",
            "height": 1086,
            "size_bytes": 994361,
            "width": 1448
          },
          "把背景改成蓝色"
        ]
      },
      "create_time": 1794797449.894,
      "end_turn": null,
      "id": "<message-id>",
      "metadata": {
        "automation_creation_attribution": {
          "origin": "conversation",
          "flow_id": "<message-id>"
        },
        "attachments": [
          {
            "height": 1086,
            "id": "file_<upload-id>",
            "library_file_id": "libfile_<library-id>",
            "mime_type": "image/png",
            "name": "source.png",
            "size": 994361,
            "source": "local",
            "width": 1448
          }
        ]
      },
      "recipient": "all",
      "status": "finished_successfully",
      "update_time": null,
      "weight": 1
    }
  ],
  "supported_encodings": ["v1"],
  "genui_state_snapshots": [],
  "client_prepare_state": "success"
}
```

关键点：

- 图片 part 本身**不带** `mime_type`；MIME 放在消息 `metadata.attachments[].mime_type`。
- 用户上传图指针是 `sediment://file_*`，不是 `file-service://`。
- 上传文件走 `/backend-api/files` 拿 `upload_url`，PUT 后用 `/backend-api/files/{id}/uploaded` 确认。
- `prepare_image_upload_ids` 传本轮上传返回的 `file_id`；`attachment_mime_types` 去重排序。

## 续聊 prepare

同一会话继续发消息时，prepare 带真实 `conversation_id` 与 `parent_message_id`，并把 dispatch/source 改成即时上下文变更：

```json
{
  "client_prepare_state": "sent",
  "conversation_id": "<conversation-id>",
  "action": "next",
  "model": "auto",
  "parent_message_id": "<last-message-id>",
  "timezone": "Asia/Shanghai",
  "timezone_offset_min": -480,
  "is_do_not_remember": false,
  "local_function_names": ["local.continue_in_work"],
  "client_prepare_dispatch": "immediate",
  "client_prepare_source": "context_change"
}
```

## SSE 事件顺序

一次正常文本回合的典型顺序：

```text
data: "v1"
data: {"type":"resume_conversation_token","kind":"topic","token":"<redacted>","conversation_id":"<id>"}
data: {"p":"","o":"add","v":{"message":{"author":{"role":"system"},"metadata":{"is_visually_hidden_from_conversation":true,...}}}}
data: {"v":{"message":{"author":{"role":"user"},"content":{"parts":["..."]},"recipient":"all","channel":null}}}
data: {"type":"input_message","input_message":{...}}
data: {"type":"title_generation","title":"...","conversation_id":"<id>"}
...若干 role=system 的隐藏消息（rebase / developer / plugin upsell）...
data: {"v":{"message":{"author":{"role":"assistant"},"content":{"content_type":"text","parts":[""]},"status":"in_progress","channel":"final"}}}
data: {"type":"message_marker","marker":"user_visible_token","event":"first"}
data: {"p":"/message/content/parts/0","o":"append","v":"收到"}
data: {"o":"patch","v":[{"p":"/message/content/parts/0","o":"append","v":"..."},{"p":"/message/end_turn","o":"replace","v":null}]}
data: {"v":[{"p":"/message/status","o":"replace","v":"finished_successfully"},{"p":"/message/end_turn","o":"replace","v":true}]}
data: {"type":"message_marker","marker":"last_token","event":"last"}
data: {"type":"message_stream_complete",...}
data: {"type":"user_signal_metadata",...}
```

解析要点：

- `conversation_id` 可能在顶层或 `v` 里，取第一次出现的值。
- 只认 `author.role == "assistant"`、`channel` 为空或 `final`、且不是 `is_visually_hidden_from_conversation` 的消息。
- 文本可能通过 `/message/content/parts/0` 的 `append`/`replace` 增量更新。
- `message_stream_complete` 可能先于 `[DONE]` 出现。

## 语音列表

真实网页端不把音色写死在前端，而是请求：

```http
GET /backend-api/settings/voices?spoken_language=zh-CN&voice_mode=advanced
Authorization: Bearer <token>
ChatGPT-Account-ID: <account-id>
```

响应结构：

```json
{
  "selected": "juniper",
  "voices": [
    {
      "voice": "juniper",
      "name": "Juniper",
      "description": "Open and upbeat",
      "accent": "American English",
      "preview_url": "https://persistent.oaistatic.com/voice/previews/juniper.zh.<hash>.m4a"
    }
  ]
}
```

`advanced` / `standard` / `zh-CN` / `en-US` 当前都返回同一组 9 个音色：

| `voice` 标识 | 显示名 | 上游描述 | 口音 |
|:--|:--|:--|:--|
| `juniper` | Juniper | Open and upbeat | American English |
| `maple` | Maple | Cheerful and candid | American English |
| `cove` | Cove | Composed and direct | American English |
| `breeze` | Breeze | Animated and earnest | American English |
| `orbit` | **Spruce** | Calm and affirming | American English |
| `glimmer` | **Sol** | Savvy and relaxed | American English |
| `ember` | Ember | Confident and optimistic | American English |
| `fathom` | **Arbor** | Easygoing and versatile | British English |
| `vale` | Vale | Bright and inquisitive | British English |

注意：

- 上游标识与显示名不完全一致：`orbit` = Spruce、`glimmer` = Sol、`fathom` = Arbor。
- `/backend-api/synthesize` 的 `voice` 参数接受上述官网标识，也接受 OpenAI 音色名（`alloy`、`ash`、`coral`、`echo`、`fable`、`onyx`、`nova`、`sage`、`shimmer`）。
- 传不存在的音色会返回 `HTTP 404 {"detail":{"message":"Voice not found","code":"voice_not_found"}}`，可用来校验音色是否真实存在。
- `voice_mode=wingman` 会额外返回 `bubbie`、`faro`、`tonada`、`rio`、`viola` 等实时语音音色，普通朗读/合成不使用。

## 生图结果消息

`GET /backend-api/conversations/{id}` 的 `messages` 中会出现：

```json
{
  "id": "<tool-message-id>",
  "author": { "role": "tool", "name": "t2uay3k.sj1i4kz", "metadata": {} },
  "content": {
    "content_type": "multimodal_text",
    "parts": [
      {
        "content_type": "image_asset_pointer",
        "asset_pointer": "sediment://file_<id>",
        "mime_type": "image/png",
        "size_bytes": 1041922,
        "width": 1254,
        "height": 1254,
        "metadata": {
          "generation": {
            "gen_id": "<gen-id>",
            "height": 1254,
            "width": 1254,
            "orientation": "square"
          }
        }
      }
    ]
  },
  "status": "finished_successfully",
  "metadata": {
    "image_gen_title": "简约红苹果插画",
    "permissions": [
      {
        "type": "notification",
        "status": "requested",
        "notification_channel_id": "image_gen"
      }
    ],
    "model_slug": "gpt-6",
    "default_model_slug": "auto"
  },
  "recipient": "all",
  "channel": "commentary"
}
```

识别规则：

- `author.role == "tool"`
- `author.name == "image_gen"` 或以 `t2uay3k` 开头
- 图片 part 的 `metadata.generation` 非空
- `asset_pointer` 为 `sediment://file_*` 或 `file-service://file_*`

下载：

```http
GET /backend-api/files/download/{file_id}?download_intent=false&inline=true&conversation_id={conversation_id}
```

返回 JSON 里的 `download_url` 指向 `https://chatgpt.com/backend-api/estuary/content?...`，再带 Bearer Token 下载二进制。
