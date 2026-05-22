FROM python:3.13-slim

WORKDIR /app

# Install system deps: Tesseract + Chromium for playwright (Turnstile bypass)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    tesseract-ocr \
    tesseract-ocr-vie \
    poppler-utils \
    libatk-1.0-0t64 \
    libatk-bridge2.0-0t64 \
    libcups2t64 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libpango-1.0-0 \
    libcairo2 \
    libasound2t64 \
    libatspi2.0-0t64 \
    libwayland-client0 \
    && pip install --no-cache-dir uv \
    && rm -rf /var/lib/apt/lists/*

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
