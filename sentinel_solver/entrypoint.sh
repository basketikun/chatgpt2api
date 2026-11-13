#!/bin/sh
set -eu

# Keep Chromium out of the image layers. This runs once at container startup;
# Playwright caches the browser under PLAYWRIGHT_BROWSERS_PATH for later restarts.
playwright install --with-deps --no-shell chromium
exec python app.py
