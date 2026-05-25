# Captcha-solver: Patchright + Chromium full + Xvfb + noVNC for manual logins.
FROM python:3.13-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DISPLAY=:99 \
    CAPTCHA_SOLVER_DATA_DIR=/data \
    CAPTCHA_SOLVER_DISPLAY=:99 \
    CAPTCHA_SOLVER_NOVNC_EXTERNAL_URL=http://localhost:6080/vnc.html?host=localhost&port=6080&autoconnect=1

# System deps: chromium runtime libs + Xvfb + x11vnc + websockify (noVNC)
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates wget curl gnupg \
        xvfb x11vnc supervisor fluxbox \
        novnc websockify \
        # Chromium runtime libraries.
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
        libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
        libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
        libatspi2.0-0 libxshmfence1 fonts-noto-cjk fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

# Install real Google Chrome — Patchright's stealth patches work best on top
# of the genuine Chrome binary, and Cloudflare Turnstile reliability is
# noticeably higher than with the Chrome-for-Testing build.
RUN wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Patchright still bundles a Chromium copy as fallback. Keep both.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN patchright install chromium

# Node + cloak-bridge: a second stealth layer on top of patchright.
# We install Node here (used only by the bridge sidecar, not Python) so the
# Python process can `httpx.post` to a localhost cloakbrowser endpoint
# instead of subprocessing Node per call. Node 20 LTS is small (~30 MB).
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install cloak-bridge dependencies separately to keep the npm cache layer
# stable across source-only changes.
COPY cloak-bridge/package.json /app/cloak-bridge/package.json
RUN cd /app/cloak-bridge && npm install --omit=dev

COPY cloak-bridge/server.js /app/cloak-bridge/server.js
COPY src /app/src
COPY supervisord.conf /etc/supervisor/conf.d/captcha-solver.conf

VOLUME ["/data"]
# 8010 = FastAPI captcha-solver, 6080 = noVNC, 8011 = cloak-bridge (internal)
EXPOSE 8010 6080

CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/captcha-solver.conf"]
