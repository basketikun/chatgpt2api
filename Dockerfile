ARG BUILDPLATFORM
ARG TARGETPLATFORM
ARG TARGETARCH

FROM --platform=$BUILDPLATFORM oven/bun:1.3.14-alpine AS web-build

WORKDIR /app/web

COPY web/package.json web/bun.lock ./
RUN bun install --frozen-lockfile

COPY VERSION /app/VERSION
COPY CHANGELOG.md /app/CHANGELOG.md
COPY web ./
RUN NEXT_PUBLIC_APP_VERSION="$(cat /app/VERSION)" bun run build


FROM --platform=$TARGETPLATFORM python:3.13-slim AS app

ARG TARGETPLATFORM
ARG TARGETARCH

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# 安装系统依赖
# - git: Git 存储后端需要
# - libpq-dev: PostgreSQL 客户端库
# - gcc: 编译 psycopg2-binary 需要
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    libpq-dev \
    gcc \
    openssl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY main.py ./
COPY config.json ./
COPY VERSION ./
COPY api ./api
COPY services ./services
COPY utils ./utils
COPY scripts ./scripts
COPY --from=web-build /app/web/out ./web_dist

EXPOSE 80

CMD ["/app/.venv/bin/uvicorn", "main:app", "--host", "0.0.0.0", "--port", "80", "--access-log"]
