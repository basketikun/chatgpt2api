# sentinel 求解服务

2026-10-14 起 chatgpt.com 的对话接口（文字和生图）开始严格校验 sentinel 握手：

- `chat-requirements` 必须带上在**真实 chatgpt.com 页面**里算出的 Turnstile token。纯 Python 模拟
  的结果会被拒，完全缺失时返回 403 "Unusual activity"。
- requirements / proof token 里编码的 UA 必须和算 Turnstile 的页面一致。
- 只要校验质量不够，对话接口不会直接返回 403，而是返回伪装成 404 的
  `{"detail":"Model not found"}` —— 主服务据此判断是账号问题还是握手质量问题。

本服务常驻一个无头 Chromium（带 playwright-stealth），一直开着 chatgpt.com 页面，替主服务计算
Turnstile。主服务本身不打包浏览器，只通过 HTTP 调用这里。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 页面状态、页面使用的 UA（主服务据此生成 requirements/proof token），以及每个 lane 抓到的 cookie |
| GET | `/health?proxy=<出口>` | 同上，额外返回 `exit`：该出口那条 lane 的 cookie 与是否已开页 |
| POST | `/v1/turnstile` | `{"dx", "p", "requirements"}` → `{"token"}`；`requirements` 是 prepare 的完整响应，给了它就调用页面自带的 turnstile 模块求解；只给 `dx`/`p` 时退回内置 VM |
| POST | `/v1/request` | 在已通过 Cloudflare 的 Chromium 页面中发送受限的 ChatGPT JSON 请求；仅允许 `/backend-api` 和 `/backend-anon` 的账号刷新及 sentinel prepare/finalize 路径 |
| POST | `/v1/so` | `{"collector_dx", "snapshot_dx", "p"}` → `{"token"}`；目前对话接口还不强制要求 |

`/health?proxy=` 是按出口取 cookie 的唯一入口：Cloudflare 对部分路径（`sentinel/chat-requirements`）
按客户端打分，同一个 curl_cffi 指纹不带这些 cookie 会被**持续性** 403 挑战（重试无效），带上同出口那条
lane 的 cookie 立刻 200。cookie 绑定签发它的出口 IP，所以接口按 lane 返回、由调用方指定自己的出口；
`/health` 不会把多条 lane 合并成一份全局 cookie（合并会让别的出口的 cookie 被静默用上）。
`?proxy=` 只读，不会顺带开页或新建 lane。

`solve` 优先走页面自带的 turnstile 模块（`import` chatgpt.com 自己的 chunk 后调用
`getEnforcementToken`）。这个 chunk 文件名带内容哈希、每次发版都变，所以运行时**动态发现**：先看页面
已加载的资源，再扫页面脚本里出现的字面路径，最后才回退到内置 VM。手写 VM 要持续跟版本，而直接调用
官方模块不需要。

设置了 `SENTINEL_SOLVER_KEY` 时，请求需要带 `Authorization: Bearer <key>` 头。

### 信任边界与代理

`/v1/request` 会接收账号 Authorization 和 JSON 请求体，并返回账号信息或 sentinel 数据。
服务端过滤 Cookie、User-Agent、Sec-*、Origin 等浏览器自管头，保留 Authorization；限制目标路径并禁止重定向。
请把 solver 当作可信服务，仅在内网提供访问，并配置访问密钥。对话 prompt 和 SSE 仍由主服务发送。
`/health` 是探活接口、不校验密钥，而它现在会带上各 lane 的 chatgpt.com cookie（`__cf_bm` / `_cfuvid`
/ `oai-did`）：这些 cookie 本身绑定出口 IP，泄露价值有限，但不能把本服务暴露到不可信网络。

账号刷新和 sentinel prepare/finalize 优先走浏览器；未配置、不可达或旧 solver 不支持此端点时回退到 curl。
真实 HTTP 401/JSON 403 直接交给原错误处理；仅 Cloudflare challenge 403 会重试——主服务把重试挂在 session
的动词上，所以图片上传、对话下载、模型列表等所有上游调用都会重试，重试前清理 Cloudflare 挑战自己留下的
cookie，但保留 solver 给的这份。三个账号刷新接口串行调用。
solver 与主服务必须使用同一出口：每个出口一条 lane，lane key 含代理凭据（住宅代理常共用同一 host:port、
靠用户名区分出口）；主服务只同步自己那条 lane 的 cookie。

## 部署

主服务通过环境变量（或 `config.json` 里的 `sentinel_solver_url` / `sentinel_solver_key`）指向本服务：

```
CHATGPT2API_SENTINEL_SOLVER_URL=http://sentinel-solver:8080
CHATGPT2API_SENTINEL_SOLVER_KEY=<与 SENTINEL_SOLVER_KEY 相同>
```

可在本目录执行 `docker build -t chatgpt2api-sentinel-solver .` 构建独立服务，容器监听 8080；
或安装 `requirements.txt`、执行 `playwright install --with-deps --no-shell chromium` 后运行 `python app.py`。
主服务无需安装 Playwright；求解服务是可选的，但遇到必需的 Turnstile 挑战时，必须配置它。

Docker 镜像不包含 Chromium；容器启动时由入口脚本下载完整 Chromium 并安装系统依赖，
成功后才启动 HTTP 服务。首次启动需要联网并以 root 安装依赖，可设置 `HTTPS_PROXY` / `HTTP_PROXY`
作为下载代理；`SENTINEL_SOLVER_PROXY` 仅控制浏览器访问 chatgpt.com 的代理。
建议将 `/ms-playwright` 挂载为持久卷，以复用已下载的浏览器；重建容器后仍需安装系统依赖。

未配置或调用失败时，主服务**直接失败**并报出明确错误，不再退回本地求解器：本地求解器跟不上新版
挑战程序，继续用空 token 只会换来伪装成 404 的 "Model not found"，白等一轮重试预算。

环境变量：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `SENTINEL_SOLVER_KEY` | 空 | 访问密钥 |
| `SENTINEL_SOLVER_PROXY` | 空 | 浏览器出网代理，应与主服务访问 chatgpt.com 的出口一致 |
| `SENTINEL_SOLVER_USER_AGENT` | 按内置 Chromium 版本生成 | 页面 UA |
| `SENTINEL_SOLVER_TIMEZONE` | 跟随系统 | 页面时区（如 `Asia/Shanghai`），应与出口 IP 所在地一致 |
| `SENTINEL_SOLVER_REFRESH_SECONDS` | 1800 | 页面定期重开的间隔 |
| `SENTINEL_SOLVER_HEADLESS` | true | 调试时可设为 false |
| `PORT` | 8080 | 监听端口 |

## 注意

- 必须使用完整 Chromium 的新版无头模式（`channel="chromium"`），并加上 stealth；默认的 headless
  shell 过不了 Cloudflare，页面会停在「请稍候…」。
- `vm.js` 移植自 chatgpt.com 前端 bundle 里的挑战程序（2026-10 版本，指令编号 0-35），来源为
  MEIZU16/chatgpt2api 的 `sentinel_solver/`（MIT），保持逐字节一致以便和前端 bundle 对账。OpenAI
  更新指令集后需要同步更新。
- 本服务只解决**请求质量问题**。被脚本批量注册、账号层面受限的账号，即使在真实网页里也会提示
  "Model not found"，那不是这里能修的。

## 来源

`vm.js` 移植自 [MEIZU16/chatgpt2api](https://github.com/MEIZU16/chatgpt2api)（MIT）；
调用页面自带 Turnstile 模块的思路来自 [239573049/WebImage](https://github.com/239573049/WebImage)（MIT）。
