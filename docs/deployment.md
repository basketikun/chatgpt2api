# Docker 部署

## 部署

```bash
git clone git@github.com:basketikun/chatgpt2api.git
cd chatgpt2api
cp config.example.yaml config.yaml
```

编辑 `config.yaml` 设置 `api-key`（或通过 `.env` 的 `CHATGPT2API_AUTH_KEY` 覆盖），然后按需选择编排文件：

| 文件 | 镜像来源 | WARP 代理 | 端口 |
| --- | --- | --- | --- |
| `docker-compose.yml` | 拉取镜像 | 不带 | 3000 |
| `docker-compose.warp.yml` | 拉取镜像 | 带 | 3000 |
| `docker-compose.local.yml` | 本地构建 | 不带 | 8000 |
| `docker-compose.local.warp.yml` | 本地构建 | 带 | 8000 |

```bash
docker compose up -d
```

其他文件用 `-f` 指定，例如 `docker compose -f docker-compose.warp.yml up -d`；本地构建加 `--build`。

- 面板：`http://localhost:3000`
- API：`http://localhost:3000/v1`

仅允许本机访问时，把编排文件里的 `3000:80` 改成 `127.0.0.1:3000:80`；直接运行二进制则设置 `BIND_ADDR=127.0.0.1`（端口仍由 `PORT` 决定）。

需要持久保留 `config.yaml`、`.env`、`data/`。数据库默认 SQLite（`data/chatgpt2api.db`），可通过 `.env` 的 `DATABASE_URL` 切换为 PostgreSQL / MySQL。

## WARP / FlareSolverr 稳定代理

带 `.warp` 的编排文件用于缓解图片链路的 Cloudflare 拦截，会同时启动：

- `warp-proxy`：提供 WARP SOCKS5 出口。
- `privoxy`：把 WARP SOCKS5 转成 HTTP 代理。
- `flaresolverr`：刷新 Cloudflare clearance。
- `app`：ChatGPT2API 主服务。

使用时把 `config.yaml` 的 `proxy_runtime.enabled` 设为 `true`，也可在后台设置页保存和测试。

只有上游 OpenAI / ChatGPT 请求走稳定代理，账号邮箱、CPA 等辅助链路不受影响。代理优先级：账号自身代理 > 稳定代理 > `config.yaml` 的全局 `proxy`。

## 升级

```bash
git pull
docker compose pull
docker compose up -d
```

## 常用命令

```bash
docker compose ps
docker logs -f chatgpt2api
```
