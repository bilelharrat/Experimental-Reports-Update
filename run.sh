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

# Claude Code installs to ~/.local/bin on macOS; ensure the server can find it
# even when the launching shell did not inherit that PATH entry.
if [ -d "${HOME}/.local/bin" ]; then
    case ":${PATH}:" in
        *":${HOME}/.local/bin:"*) ;;
        *) export PATH="${HOME}/.local/bin:${PATH}" ;;
    esac
fi

# Ensure backend deps are installed.
uv sync --quiet

# Build the frontend if it exists and the dist is missing or stale.
if [ -d "frontend" ]; then
    if [ ! -d "frontend/node_modules" ]; then
        echo "Installing frontend dependencies..."
        (cd frontend && npm install --silent)
    fi

    # dist/ is gitignored, so a pull or merge updates source without ever
    # touching the built bundle. Compare every input that changes the build
    # against dist/index.html; anything newer means the served UI is stale.
    FRONTEND_SOURCES=(
        frontend/src
        frontend/public
        frontend/index.html
        frontend/vite.config.js
        frontend/tailwind.config.cjs
        frontend/postcss.config.cjs
        frontend/package.json
        frontend/package-lock.json
    )
    DIST_STALE=0
    if [ ! -f "frontend/dist/index.html" ]; then
        DIST_STALE=1
    else
        for src in "${FRONTEND_SOURCES[@]}"; do
            [ -e "$src" ] || continue
            if [ -n "$(find "$src" -newer frontend/dist/index.html -print -quit 2>/dev/null)" ]; then
                echo "Frontend build is stale ($src changed since the last build)."
                DIST_STALE=1
                break
            fi
        done
    fi

    if [ "$DIST_STALE" = "1" ] || [ "${REBUILD_FRONTEND:-0}" = "1" ]; then
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
