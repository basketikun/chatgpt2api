#!/bin/sh
set -e

# 1. Ensure persistent data directory exists
mkdir -p /app/data

# 2. Initialize /app/data/config.json if not present
if [ ! -f /app/data/config.json ]; then
    if [ -f /app/config.json.template ]; then
        cp /app/config.json.template /app/data/config.json
    elif [ -f /app/config.json ] && [ ! -d /app/config.json ] && [ ! -L /app/config.json ]; then
        cp /app/config.json /app/data/config.json
    fi
fi

# 3. Create symlink from /app/config.json to persistent /app/data/config.json
if [ -f /app/data/config.json ]; then
    if [ ! -L /app/config.json ] && [ ! -d /app/config.json ]; then
        rm -f /app/config.json 2>/dev/null || true
        ln -sf /app/data/config.json /app/config.json 2>/dev/null || true
    fi
    export CHATGPT2API_CONFIG_FILE=/app/data/config.json
fi

# 4. Default storage backend settings if not explicitly specified
if [ -z "$STORAGE_BACKEND" ]; then
    export STORAGE_BACKEND=sqlite
fi

if [ "$STORAGE_BACKEND" = "sqlite" ] && [ -z "$DATABASE_URL" ]; then
    export DATABASE_URL="sqlite:////app/data/accounts.db"
fi

exec "$@"
