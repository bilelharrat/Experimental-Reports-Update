# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1 — build the Vue SPA.
#
# run.sh builds the frontend at startup, which is right for a laptop and wrong
# for a container: it would drag the whole dev toolchain into the runtime image
# and rebuild on every restart. Here dist/ is baked in, so the image is the
# deployable unit.
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


# ---------------------------------------------------------------------------
# Stage 2 — runtime.
#
# Based on the Node image rather than the Python one because claude_runner.py
# shells out to the `claude` CLI, which is a Node program. Debian bookworm's
# system python3 is 3.11, which satisfies pyproject's requires-python.
# ---------------------------------------------------------------------------
FROM node:22-bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# chromium      — browser_archive.py renders difficult pages with headless
#                 Chrome; "chromium" is in its DEFAULT_CHROME_CANDIDATES.
# pandoc        — claude_runner prompts the agent to convert docx/PDF with it.
# fonts-noto-cjk— the memos are Chinese. Without CJK fonts every headless
#                 Chrome render comes out as tofu boxes.
# git           — the agent runs in a working directory and expects it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-venv \
        chromium \
        pandoc \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        ca-certificates \
        curl \
        git \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# The `claude` CLI. Baked into the image on purpose: the image is the unit of
# reproducibility, and credentials live in $HOME (a volume), not here — so a
# rebuild upgrades the CLI without logging anyone out.
RUN npm install -g @anthropic-ai/claude-code

# uv as a standalone binary.
ENV UV_INSTALL_DIR=/usr/local/bin
RUN curl -LsSf https://astral.sh/uv/install.sh | sh

RUN useradd --create-home --uid 10001 app

WORKDIR /app

ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON=/usr/bin/python3 \
    UV_PYTHON_DOWNLOADS=never \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    TZ=America/Los_Angeles \
    MPLBACKEND=Agg \
    MPLCONFIGDIR=/tmp/mpl

# Dependencies before source: this layer only rebuilds when the lock changes,
# so a code-only redeploy skips the whole dependency install.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY server/ ./server/
# Editorial memo prompts (company-type lenses, structures, zh twins) live
# at the repo root so the founder's team can edit them without touching
# server code; the runtime resolves them relative to server/.
COPY skills/ ./skills/
COPY --from=frontend /build/dist ./frontend/dist
RUN uv sync --frozen --no-dev

# A fresh named volume inherits the ownership of whatever is at its mount
# point in the image, so these have to exist and be owned by `app` first.
RUN mkdir -p /app/data /home/app/.claude \
    && chown -R app:app /app /home/app

USER app
ENV HOME=/home/app

# Documentation only — this port is never published. Envoy reaches it over the
# private_web network. See ec2-docker-ingress-architecture.md.
EXPOSE 8010

# root_path="/research" is hardcoded in main.py, and Starlette strips that
# prefix before routing, so the health route answers on both paths. Probing
# the prefixed one mirrors what Envoy actually sends.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8010/research/health || exit 1

CMD ["uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8010"]
