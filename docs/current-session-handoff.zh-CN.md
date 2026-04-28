# ChatGPT2API 当前项目交接文档

最后更新：2026-04-28

本文用于下次新会话快速恢复上下文。建议新会话开始时先读取本文件，再结合 `git status --short`、最新 `logs/ops/image-*.log` 和相关源码继续处理。

## 1. 项目当前定位

当前项目是一个自托管的 ChatGPT/OpenAI 兼容图片能力代理，重点能力集中在：

- Web 图片工作台：`/image`
- 提示词素材页：`/prompts`
- 登录页：`/login`
- OpenAI 兼容图片 API：`/v1/images/generations`、`/v1/images/edits`
- 面向图片工作流的兼容接口：`/v1/chat/completions`、`/v1/responses`

当前工作区已经明显向“图片生成/编辑工作台 + 图片 API 代理”收敛。账号管理页、设置页、CPA 导入相关代码在当前工作区状态里已被删除或移除，需要后续确认这是产品裁剪还是误删。

## 2. 关键决策

### 2.1 图片会话按多轮线程建模

图片历史不再是“一条记录只对应一次生成”，而是一个会话下包含多轮 `turns`。

核心决策：

- `ImageConversation` 保存 `createdAt`、`updatedAt` 和 `turns`。
- 每次用户在已选中的图片会话内继续发送提示词，追加一个新的 `ImageConversationTurn`。
- 旧版本单轮历史通过 `buildLegacyTurn()` 自动归一化为一轮 `turn`，避免破坏已有本地历史。
- 侧边栏按 `updatedAt` 排序，最近继续编辑的会话浮到上方。

主要文件：

- `web/src/store/image-conversations.ts`
- `web/src/app/image/page.tsx`
- `web/src/app/image/components/image-results.tsx`

### 2.2 同一图片会话内继续对话默认进入编辑图流程

用户反馈“第二次提示词会新开会话/无法修改已生成图片”。当前处理思路是让同一会话内的后续提示词走图片编辑，而不是重新文生图。

核心决策：

- 选择已有图片会话时，如果该会话有成功图片，自动切换到 `edit` 模式。
- 一轮图片生成成功后，输入区自动切换到 `edit` 模式。
- 编辑模式未手动上传参考图时，默认取当前会话最近一轮成功图片作为编辑输入。
- 如果用户要重新从零生图，需要点击“新建对话”或手动切回文生图。

主要文件：

- `web/src/app/image/page.tsx`
- `web/src/app/image/components/image-composer.tsx`

### 2.3 Chat Completions / Responses 多轮图片上下文兼容

兼容接口本身不是完整聊天代理，只服务图片工作流。

核心决策：

- `/v1/chat/completions` 只取最新一轮 user prompt，不再拼接所有历史 user 文本。
- `/v1/responses` 只取当前输入或 trailing `input_text`。
- 如果最新 user 输入没有显式图片，则从上一轮 assistant 返回内容中提取 data URL 图片，作为本轮编辑输入。
- assistant 返回的 Markdown 图片 `![image](data:image/png;base64,...)` 可被后续轮次继承。

主要文件：

- `services/utils.py`
- `services/chatgpt_service.py`
- `test/test_image_context.py`

### 2.4 OpenAI 图片上游改用标准库 HTTPS 请求

用户在编辑图续聊时遇到：

```text
curl: (35) TLS connect error ... OPENSSL_internal:invalid library
```

日志确认请求已走 `/images/edits`，失败发生在 `curl_cffi` TLS 握手阶段，不是业务参数或提示词问题。

核心决策：

- `services/openai_image_service.py` 的 OpenAI 兼容图片上游请求改为 `urllib.request`。
- 文生图仍发 JSON 到 `/images/generations`。
- 编辑图使用 multipart/form-data 到 `/images/edits`，字段名为 `image`。
- 保留原有重试、日志事件和错误包装。
- `URLError`、`SSLError`、连接中断、超时、JSON 截断等都作为可重试异常。

主要文件：

- `services/openai_image_service.py`
- `test/test_openai_image_service.py`

### 2.5 前端配额显示改为运行时摘要

由于当前工作区中账号管理 UI 已删除，图片页不再通过账号列表计算配额。

核心决策：

- 新增/使用 `/api/runtime` 返回运行时摘要。
- 前端通过 `fetchRuntimeStatus()` 获取 `available_quota` 和 `image_upstream`。
- 当前 `web/src/lib/api.ts` 只保留登录、runtime、图片生成、图片编辑、提示词优化相关 API。

主要文件：

- `services/api.py`
- `web/src/lib/api.ts`
- `web/src/app/image/page.tsx`

### 2.6 运行方式以 Docker + 本地挂载为主

当前 `docker-compose.yml`：

- 容器名：`chatgpt2api`
- 端口：`127.0.0.1:3001:80`
- 挂载：
  - `./data:/app/data`
  - `./logs:/app/logs`
  - `./config.json:/app/config.json:ro`
  - `./services:/app/services:ro`
  - `./web/out:/app/web_dist:ro`

后端服务代码通过 `./services` 挂载进入容器，重启容器即可加载后端 Python 修改。

前端是静态导出，`web/next.config.ts` 使用 `output: "export"`，修改前端源码后需要先执行：

```powershell
cd E:\chatgpt2api\web
npm run build
cd E:\chatgpt2api
docker restart chatgpt2api
```

## 3. 已完成部分

### 3.1 Web 图片工作台

- 已把图片历史改造成多轮会话线程。
- 已支持同一会话内继续发送提示词追加新轮次。
- 已支持编辑模式隐式复用当前会话最近一轮生成图。
- 已在选中已有图片会话和生成成功后自动切到编辑图模式。
- 已按轮次渲染 prompt、参考图、模型、张数、时间、状态、结果图和错误信息。
- 已保留旧历史记录读取兼容逻辑。

### 3.2 后端图片 API

- `/v1/images/generations` 支持 OpenAI 图片上游或 ChatGPT 账号池 fallback。
- `/v1/images/edits` 支持上传一张或多张图片，并转发到上游 multipart 编辑接口。
- `/v1/chat/completions` 和 `/v1/responses` 支持从历史 assistant 图片继承编辑输入。
- 提示词优化接口 `/api/image-prompts/optimize` 已接入模型优化和 fallback 优化。
- 图片结果保存到 `data/images`，响应中补充 `file_name`、`file_path`、`file_size`。

### 3.3 日志与排障

- 图片链路日志已拆成：
  - `logs/ops/*.log`：面向人工排障的中文摘要日志。
  - `logs/ai/*.jsonl`：结构化事件日志。
- 日志事件覆盖请求开始、上游尝试、上游响应、重试等待、保存图片、请求失败等。
- 已确认最近一次 TLS 报错发生在 `/images/edits` 上游连接阶段，之后已替换传输层。

### 3.4 构建、测试与重启

已执行并通过：

```powershell
cd E:\chatgpt2api\web
npm run build
npx tsc --noEmit
```

```powershell
cd E:\chatgpt2api
.\.venv\Scripts\python.exe -m unittest discover -s test -p "test_image_context.py" -t .
.\.venv\Scripts\python.exe -m unittest discover -s test -p "test_openai_image_service.py" -t .
.\.venv\Scripts\python.exe -m py_compile services\openai_image_service.py
```

最近一次服务重启：

```text
container: chatgpt2api
status: running
started_at: 2026-04-28T08:57:52.509257438Z
port: 127.0.0.1:3001 -> 80
```

## 4. 待办事项

### 4.1 立即验证

- 重启后需要实际再跑一次同会话续编图片，确认 `urllib` 传输层消除了 `curl: (35)` TLS 错误。
- 如果仍失败，优先查看最新 `logs/ops/image-*.log`，判断是 TLS、HTTP 4xx/5xx、上游模型不可用，还是图片输入内容问题。
- 如果出现 `model_not_found` 或 “No available channel for model gpt-image-2”，需要切换模型到 `gpt-image-1` 或调整上游渠道配置。

### 4.2 产品范围确认

当前工作区有以下删除，需要确认是否为预期裁剪：

- `web/src/app/accounts/page.tsx`
- `web/src/app/accounts/components/account-import-dialog.tsx`
- `web/src/app/settings/page.tsx`
- `services/cpa_service.py`
- `assets/account_pool.png`

如果这些不是有意删除，应从版本控制中恢复或重新合并相关功能。当前前端导航和 API 类型已经向图片工作台收敛，恢复时需要同步改回 `web/src/lib/api.ts` 和相关路由。

### 4.3 文案编码问题

仓库中多处中文出现 mojibake，例如 `绂佺敤`、`鍔犺浇`、`鐢熸垚` 等。

风险：

- 用户界面中文显示异常。
- 日志中文摘要可读性下降。
- 字符串比较可能出错，例如账号状态 `"禁用"` 被 mojibake 后比较不可靠。

建议：

- 统一确认文件编码为 UTF-8。
- 修复前端 UI 文案、日志文案、配置错误文案。
- 修复后跑 `npm run build`、`npx tsc --noEmit` 和相关 Python 测试。

### 4.4 配置和密钥安全

`services/config.py` 当前包含 OpenAI 图片上游和提示词优化上游的默认 base URL / API key 常量。

风险：

- 如果仓库会推送或分享，存在密钥泄露风险。
- 环境迁移时不利于部署配置隔离。

建议：

- 改成优先环境变量，其次 `config.json`，最后空值或安全占位。
- 轮换已经写入仓库或日志的真实密钥。
- 文档中只记录变量名，不记录明文密钥。

### 4.5 错误体验

当前前端会直接展示上游错误字符串。

建议：

- 对常见错误做用户友好映射：
  - 缺少图片输入。
  - TLS/网络连接失败。
  - 上游模型不可用。
  - 内容策略或请求被拒。
  - 上游超时。
- 保留“查看完整错误”用于排障，不把长错误塞进主结果卡片。

### 4.6 测试补强

已有定向单测：

- `test/test_image_context.py`
- `test/test_openai_image_service.py`

建议补充：

- 前端同会话续编的 E2E 测试。
- 后端 `/v1/images/edits` multipart 入参到上游请求的集成测试。
- 失败后部分图片成功、部分失败的状态持久化测试。
- 本地历史从旧单轮结构迁移到 `turns` 的测试。

## 5. 重要文件修改记录

### 后端

| 文件 | 当前职责 / 重要改动 |
|---|---|
| `services/api.py` | FastAPI 路由入口；图片生成、图片编辑、提示词优化、runtime 摘要、静态 Web 分发。 |
| `services/openai_image_service.py` | OpenAI 兼容图片上游；已改为 `urllib.request`；支持 JSON 生图和 multipart 编辑；保留重试和日志。 |
| `services/image_service.py` | ChatGPT 官网逆向图片生成/编辑实现；账号池 fallback 使用。 |
| `services/chatgpt_service.py` | OpenAI 兼容 chat/responses 图片工作流包装；支持多轮 assistant 图片继承。 |
| `services/utils.py` | 消息 prompt 和图片提取工具；只取最新 user prompt；支持从 Markdown/data URL 提取图片。 |
| `services/image_file_store.py` | 保存返回图片到 `data/images` 并补充文件元信息。 |
| `services/image_prompt_optimizer.py` | 提示词优化接口实现；模型优化失败时 fallback。 |
| `services/image_trace_logger.py` | 图片链路 ops/ai 双日志。 |
| `services/config.py` | 应用配置；当前存在默认上游 URL/API key 常量，需要安全处理。 |

### 前端

| 文件 | 当前职责 / 重要改动 |
|---|---|
| `web/src/app/image/page.tsx` | 图片工作台主状态；多轮会话、续聊编辑、隐式参考图、runtime 配额。 |
| `web/src/store/image-conversations.ts` | localforage 图片历史；`turns` 数据结构；旧历史兼容迁移。 |
| `web/src/app/image/components/image-results.tsx` | 按轮次展示图片会话结果、参考图、错误详情。 |
| `web/src/app/image/components/image-composer.tsx` | 输入区；编辑图参考图上传；提示隐式复用上一轮图片。 |
| `web/src/app/image/components/image-sidebar.tsx` | 会话列表；按 `updatedAt` 显示最近更新时间。 |
| `web/src/lib/api.ts` | 当前仅保留登录、runtime、提示词优化、图片生成、图片编辑 API。 |
| `web/src/app/prompts/page.tsx` | 提示词素材页，当前仍保留。 |
| `web/src/components/top-nav.tsx` | 顶部导航，当前应与已保留页面同步。 |

### 测试与文档

| 文件 | 当前职责 / 重要改动 |
|---|---|
| `test/test_image_context.py` | 验证 chat/responses 多轮图片上下文继承和最新 prompt 提取。 |
| `test/test_openai_image_service.py` | 验证 `urllib` 上游响应解析和 URL/TLS 错误可重试。 |
| `docs/logging.zh-CN.md` | 图片链路日志说明。 |
| `docs/feature-status.en.md` | 功能状态说明，当前可能需要按产品裁剪结果更新。 |
| `docs/current-session-handoff.zh-CN.md` | 本交接文档。 |

## 6. 当前工作区状态摘要

截至本文件创建时，`git status --short` 显示工作区未提交且包含较多修改、删除和新增文件。

特别注意：

- 有大量产品裁剪相关删除，后续提交前必须确认是否符合预期。
- `web/out` 已在 2026-04-28 17:21 左右重新生成，容器通过该目录提供静态前端。
- 后端 `services` 目录通过 Docker volume 挂载，重启容器即可加载 Python 修改。
- 当前容器名固定为 `chatgpt2api`。

常用检查命令：

```powershell
git status --short
git diff --stat
docker ps --filter "name=chatgpt2api"
docker logs --tail 100 chatgpt2api
```

## 7. 继续工作的建议顺序

1. 先实际验证 `/image` 同会话续编是否成功。
2. 若失败，读取最新 `logs/ops/image-*.log` 和对应 `logs/ai/image-*.jsonl`。
3. 处理上游错误分类和前端错误文案。
4. 确认账号页、设置页、CPA 服务删除是否为预期。
5. 修复 mojibake 文案和配置密钥风险。
6. 补充 E2E 或集成测试。
7. 最后再整理 README、feature status 和发布说明。

## 8. 下次新会话建议加载的文件

优先读取：

```text
docs/current-session-handoff.zh-CN.md
services/api.py
services/openai_image_service.py
services/utils.py
services/chatgpt_service.py
web/src/app/image/page.tsx
web/src/store/image-conversations.ts
web/src/lib/api.ts
```

排障时读取：

```text
logs/ops/latest image log
logs/ai/latest image jsonl
test/test_image_context.py
test/test_openai_image_service.py
docker-compose.yml
```
