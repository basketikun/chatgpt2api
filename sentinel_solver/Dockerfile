ARG PYTHON_IMAGE=python:3.13-slim

FROM ${PYTHON_IMAGE}

# Build-time proxy for pip and the Chromium download (same convention as the app image).
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG http_proxy
ARG https_proxy

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

COPY requirements.txt ./
# 只安装完整 Chromium（新版无头模式），headless shell 过不了 Cloudflare
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py turnstile_result.py vm.js entrypoint.sh ./
RUN sed -i 's/\r$//' entrypoint.sh && chmod +x entrypoint.sh

EXPOSE 8080
ENTRYPOINT ["/app/entrypoint.sh"]
