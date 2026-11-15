# 上游 Conversation SSE 协议说明

Conversation SSE 是上游对话链路的流式返回协议。每条 SSE `data:` 通常是一段 JSON payload，也可能是协议标记或结束标记。客户端需要按顺序消费这些 payload，维护当前会话状态、文本内容、工具调用状态和图片结果指针。

## 请求载荷（2026-11-16 真实浏览器抓包）

`POST /backend-api/f/conversation` 当前提交字段：

| 字段 | 说明 |
|:--|:--|
| `turn_attribution` | `{"turn_trigger":"composer"}` |
| `action` | 固定 `next` |
| `messages` | 消息数组；每条消息带 `author`、`content`、`metadata`、`channel`、`recipient`、`status`、`end_turn`、`weight`、`update_time` |
| `model` | 上游模型 slug，例如 `auto`、`gpt-6`、`gpt-6-mini` |
| `parent_message_id` | 新会话为 `client-created-root` |
| `supported_encodings` | `["v1"]` |
| `genui_state_snapshots` | `[]` |
| `client_prepare_state` | 准备成功后为 `success` |
| `system_hints` | 仅在搜索 / 生图等场景出现，例如 `["search"]`、`["picture_v2"]`、`["reason"]` |
| `thinking_effort` | 用户选择思考强度时出现；按账号/模型透传 `low` / `medium` / `high` / `standard` / `extended` / `xhigh` / `max` / `ultra` 等档位 |
| `client_contextual_info` | `app_name`、`app_surface`、`has_web_push_capabilities`、`web_push_notification_permission` |
| `is_do_not_remember` | 是否不记忆 |
| `force_use_search` | 搜索轮次为 `true` |
| `timezone` / `timezone_offset_min` | 时区与偏移 |

普通文本对话**不发送** `conversation_mode`，也**不使用** `supports_buffering`、`force_parallel_switch`、`paragen_cot_summary_display_override`、`enable_message_followups`。

准备请求 `POST /backend-api/f/conversation/prepare` 是精简载荷，不带 `messages` / `partial_query`：

```json
{"client_prepare_state":"sent","action":"next","model":"auto","parent_message_id":"client-created-root","timezone":"Asia/Shanghai","timezone_offset_min":-480,"is_do_not_remember":false,"system_hints":["picture_v2"],"local_function_names":["local.continue_in_work"],"client_prepare_dispatch":"debounced","client_prepare_source":"composer_editor_state"}
```

响应中的 `conduit_token` 需要作为 `x-conduit-token` 带回正式请求。续聊时 prepare 额外带 `conversation_id`、真实的 `parent_message_id`，`client_prepare_dispatch` 为 `immediate`、`client_prepare_source` 为 `context_change`；带图时额外带 `attachment_mime_types`（去重排序）与 `prepare_image_upload_ids`（本轮上传的 `file_id`）。

相关接口与请求头：

| 用途 | 方法与路径 |
|:--|:--|
| 提交一轮对话 | `POST /backend-api/f/conversation` |
| 准备 / 换取 conduit token | `POST /backend-api/f/conversation/prepare` |
| 读取会话详情 | `GET /backend-api/conversations/{conversation_id}?num_turns=10&include_has_versions=true` |
| 读取会话 init / 额度 | `POST /backend-api/conversation/init` |
| 删除会话 | `DELETE /backend-api/conversation/id/{conversation_id}` |

正式请求需要同时带上 `Authorization: Bearer <access_token>`、`x-conduit-token`、`x-oai-turn-trace-id`、`x-oai-mcp-form-version: 2`，以及 sentinel 的 `OpenAI-Sentinel-Chat-Requirements-Token`（如触发 PoW / Turnstile 还需对应 token）。真实网页端还会带 `originator: Codex Browser`、`x-openai-web-frontend: codex_webview`、`x-openai-codex-window-type: browser`、`oai-did`、`ChatGPT-Account-Id` 等指纹头。

完整抓包记录见 [upstream-capture-2026-11-16.md](upstream-capture-2026-11-16.md)。

## 基本形态

常见 payload 示例：

```text
"v1"
{"type":"resume_conversation_token",...}
{"p":"","o":"add","v":{...}}
{"v":{...}}
{"p":"/message/content/parts/0","o":"append","v":"..."}
{"type":"server_ste_metadata","metadata":{...}}
[DONE]
```

处理建议：

| payload | 含义 | 处理方式 |
|:--|:--|:--|
| `"v1"` | 协议版本标记 | 可记录，通常不影响业务 |
| `[DONE]` | 当前 SSE 流结束 | 停止继续读取 |
| JSON object | 事件、消息或 patch | 按字段更新会话状态 |
| JSON string | 短文本 patch 或协议标记 | 结合上下文处理 |
| 非 JSON 内容 | 原始内容 | 保留为 raw 事件，避免中断流 |

## 常用字段

| 字段 | 说明 |
|:--|:--|
| `type` | 上游事件类型，如 `resume_conversation_token`、`input_message`、`message_marker`、`title_generation`、`server_ste_metadata`、`message_stream_complete`、`user_signal_metadata`、`paragen` |
| `conversation_id` | 当前会话 ID，可从多个事件中获得 |
| `p` | patch 路径，例如 `/message/content/parts/0` |
| `o` | patch 操作，例如 `add`、`append`、`replace`、`patch` |
| `v` | patch 值，可能是字符串、数组，也可能包含完整 message |
| `c` | 消息序号或游标，常见于 add 类事件 |
| `message.id` | 消息 ID |
| `message.author.role` | 消息角色，常见 `system`、`user`、`assistant`、`tool` |
| `message.content.content_type` | 内容类型，如 `text`、`multimodal_text`、`model_editable_context` |
| `message.content.parts` | 内容片段，可能包含文本、图片指针或多模态对象 |
| `message.status` | 消息状态，如 `in_progress`、`finished_successfully` |
| `message.end_turn` | 是否结束当前轮次 |
| `metadata.tool_invoked` | 本轮是否调用工具 |
| `metadata.turn_use_case` | 本轮用途，如 `text`、`multimodal` |
| `metadata.generation` | 图片生成结果元数据；图片 part 里非空才视为生成图 |
| `author.name` | 图片工具名为 `image_gen` 或以 `t2uay3k` 开头 |

## 会话启动事件

上游通常会先返回恢复令牌或会话令牌：

```json
{
  "type": "resume_conversation_token",
  "kind": "topic",
  "token": "...",
  "conversation_id": "..."
}
```

这个事件主要用于标识会话和恢复上下文。业务层通常只需要保存 `conversation_id`，`token` 不应该暴露给下游用户。

## 消息 add 场景

完整消息可能通过 `add` 或带 `v.message` 的事件出现：

```json
{
  "p": "",
  "o": "add",
  "v": {
    "message": {
      "author": {"role": "assistant"},
      "content": {"content_type": "text", "parts": [""]},
      "status": "in_progress"
    },
    "conversation_id": "..."
  },
  "c": 3
}
```

此类事件常用于创建一条新消息。若消息角色为 `assistant`，后续文本通常会通过 patch 继续追加。

## 文本增量场景

文本输出通常由多条 patch 组成：

```json
{"p":"/message/content/parts/0","o":"append","v":"Hello"}
{"v":" world"}
{"p":"","o":"patch","v":[
  {"p":"/message/content/parts/0","o":"append","v":"!"},
  {"p":"/message/status","o":"replace","v":"finished_successfully"},
  {"p":"/message/end_turn","o":"replace","v":true}
]}
```

处理要点：

| 形态 | 含义 |
|:--|:--|
| `p == "/message/content/parts/0"` 且 `o == "append"` | 向当前文本追加内容 |
| `o == "replace"` | 用新值替换目标字段 |
| `o == "patch"` 且 `v` 是数组 | 批量 patch，需要按数组顺序处理 |
| 只有 `v` 且 `v` 是字符串 | 可能是省略路径的文本增量，应结合当前文本流处理 |

## 输入消息场景

用户输入会以 `input_message` 或普通 `user` message 出现。图片编辑请求会包含用户上传的参考图：

```json
{
  "type": "input_message",
  "input_message": {
    "author": {"role": "user"},
    "content": {
      "content_type": "multimodal_text",
      "parts": [
        {"asset_pointer": "sediment://file_input"},
        "编辑提示词"
      ]
    }
  },
  "conversation_id": "..."
}
```

这类 `sediment://...` 表示输入附件，不是生成结果。即使它可以被下载，也不能当作输出图片返回。

## 图片工具成功场景

图片生成或图片编辑成功时，上游一般会出现工具消息：

```json
{
  "v": {
    "message": {
      "author": {"role": "tool", "name": "t2uay3k.sj1i4kz", "metadata": {}},
      "content": {
        "content_type": "multimodal_text",
        "parts": [
          {
            "content_type": "image_asset_pointer",
            "asset_pointer": "sediment://file_result",
            "mime_type": "image/png",
            "size_bytes": 1041922,
            "width": 1254,
            "height": 1254,
            "metadata": {"generation": {"gen_id": "...", "width": 1254, "height": 1254}}
          }
        ]
      },
      "metadata": {"image_gen_title": "...", "model_slug": "gpt-6", "default_model_slug": "auto"},
      "channel": "commentary"
    }
  },
  "conversation_id": "..."
}
```

只有同时满足以下条件的图片指针，才应该视为输出结果：

| 条件 | 说明 |
|:--|:--|
| `message.author.role == "tool"` | 来源是工具消息 |
| `message.author.name` 为 `image_gen` 或以 `t2uay3k` 开头 | 当前图片工具名 |
| 图片 `metadata.generation` 非空 | 表示是生成结果而不是输入附件 |
| `asset_pointer` 为 `file-service://...` 或 `sediment://...` | 指向可解析图片资源 |

图片消息也可能出现在 `metadata.image_gen_async == true` 的异步轮次中，此时需要继续轮询会话直到图片出现。

## 图片指针类型

| 指针 | 常见来源 | 说明 |
|:--|:--|:--|
| `file-service://file_xxx` | 图片工具输出 | 可通过文件下载接口解析 |
| `sediment://file_xxx` | 输入附件或图片工具输出 | 需要结合消息角色判断来源 |
| `file_upload` | 上传过程占位 | 通常不应作为输出 |

不要只凭字符串里出现 `file_` 或 `sediment://` 就判定为输出图。必须结合消息角色和任务类型。

## 策略拒绝场景

当上游拒绝请求时，通常不会产生图片工具消息，而是返回普通 assistant 文本：

```text
I can't assist with that request. If you have another type of modification...
```

常见伴随事件：

```json
{"type":"title_generation","title":"Request Denied","conversation_id":"..."}
```

```json
{
  "type": "server_ste_metadata",
  "metadata": {
    "tool_invoked": false,
    "turn_use_case": "multimodal",
    "did_prompt_contain_image": true
  },
  "conversation_id": "..."
}
```

处理要点：

| 条件 | 行为 |
|:--|:--|
| 有 assistant 拒绝文本 | 应返回文本消息 |
| `tool_invoked == false` | 说明没有实际工具结果 |
| 没有 `role=tool` 且图片 `metadata.generation` 非空的消息 | 不应收集输出图片 |
| 用户输入消息里有图片指针 | 仍然只视为输入附件 |

## moderation 场景

部分请求可能返回 moderation 事件：

```json
{
  "type": "moderation",
  "moderation_response": {
    "blocked": true
  },
  "conversation_id": "..."
}
```

若 `blocked == true`，应认为本轮被策略拦截。后续如有 assistant 文本，应优先返回该文本；若没有文本，可返回合适的错误信息。

## marker 和 title 事件

上游会返回一些辅助事件：

```json
{"type":"message_marker","marker":"user_visible_token","event":"first"}
{"type":"message_marker","marker":"last_token","event":"last"}
{"type":"title_generation","title":"...","conversation_id":"..."}
```

这些事件通常用于前端展示、标题生成或流式状态标记，不代表实际文本内容或图片结果。

## metadata 事件

`server_ste_metadata` 用于描述本轮调度和工具状态：

```json
{
  "type": "server_ste_metadata",
  "metadata": {
    "tool_invoked": true,
    "turn_use_case": "multimodal",
    "model_slug": "i-mini-m",
    "did_prompt_contain_image": true
  }
}
```

常用判断：

| 字段 | 说明 |
|:--|:--|
| `tool_invoked == true` | 上游认为本轮调用过工具 |
| `tool_invoked == false` | 上游未调用工具，常见于拒绝或纯文本响应 |
| `turn_use_case == "text"` | 按文本响应处理 |
| `turn_use_case == "multimodal"` | 多模态请求，不代表一定有图片输出 |
| `did_prompt_contain_image == true` | 输入包含图片，不代表输出包含图片 |

## 结束后的结果判断

SSE 结束后可按以下顺序判断结果：

1. 如果已经收集到图片工具输出指针，解析并下载输出图片。
2. 如果没有输出图片指针，但有 assistant 文本，并且本轮被拦截或未调用工具，返回文本消息。
3. 如果没有输出图片指针，但有 `conversation_id`，可查询完整会话明细，继续寻找图片工具输出。新会话的详情可能只返回 `mapping` 节点树而 `messages` 为空，需要遍历 `mapping[*].message`。
4. 查询完整会话时，仍然只读取 `author.role == "tool"` 且图片 `metadata.generation` 非空的消息。
5. 如果没有图片结果也没有文本，返回上游异常或空结果错误。

