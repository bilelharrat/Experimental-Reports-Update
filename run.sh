#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Load .env if present so service config is available without exporting.
if [ -f .env ]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
fi

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8010}"

# Ensure backend deps are installed.
uv sync --quiet

# Build the frontend if it exists and the dist is missing/stale.
if [ -d "frontend" ]; then
    if [ ! -d "frontend/node_modules" ]; then
        echo "Installing frontend dependencies..."
        (cd frontend && npm install --silent)
    fi
    if [ ! -f "frontend/dist/index.html" ] || [ "${REBUILD_FRONTEND:-0}" = "1" ]; then
        echo "Building frontend..."
        (cd frontend && npm run build)
    fi
fi

mkdir -p data

if [ "$HOST" = "0.0.0.0" ]; then
    LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)"
    echo "Starting server on http://127.0.0.1:${PORT}${LAN_IP:+ and http://${LAN_IP}:${PORT}}"
else
    echo "Starting server on http://${HOST}:${PORT}"
fi
exec uv run uvicorn server.main:app --host "$HOST" --port "$PORT" "$@"
