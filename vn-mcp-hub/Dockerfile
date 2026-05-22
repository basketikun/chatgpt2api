FROM python:3.13-slim

WORKDIR /app

# Install only what sentence-transformers needs, then purge build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    tesseract-ocr-vie \
    poppler-utils \
    wget \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/*

# Install cloudflared for Cloudflare Tunnel support
RUN ARCH=$(dpkg --print-architecture) && \
    case "$ARCH" in \
      amd64) CF_ARCH="amd64" ;; \
      arm64) CF_ARCH="arm64" ;; \
      *) echo "Unsupported architecture: $ARCH"; exit 1 ;; \
    esac && \
    wget -q "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${CF_ARCH}.deb" -O /tmp/cloudflared.deb && \
    dpkg -i /tmp/cloudflared.deb && \
    rm /tmp/cloudflared.deb

COPY pyproject.toml ./
RUN uv pip install --system --no-cache . \
    && apt-get purge -y build-essential binutils gcc g++ cpp make \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* \
    && find /usr/local/lib/python*/site-packages -name "*.pyc" -delete \
    && find /usr/local/lib/python*/site-packages -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

COPY src/ ./src/
COPY data/ ./data/

RUN mkdir -p /app/chroma_db

EXPOSE 8005
# Force cache bust 2026-05-22 v3 (fix markitdown pdf dep)

CMD ["python", "-m", "src.main"]
