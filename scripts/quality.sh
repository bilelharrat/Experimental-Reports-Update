#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

run() {
  printf '+'
  printf ' %q' "$@"
  printf '\n'
  "$@"
}

NEW_HYPOTHESIS_PY=(
  server/hypothesis_store.py
  server/hypothesis_cycle.py
  tests/test_hypothesis_store.py
  tests/test_hypothesis_cycle.py
)

run uv sync --locked
run uv run ruff check server scripts tests
run uv run ruff check --select E4,E7,E9,F "${NEW_HYPOTHESIS_PY[@]}"
run uv run ruff format --check "${NEW_HYPOTHESIS_PY[@]}"
run python -m pytest
run python -m py_compile \
  server/stock_research.py \
  server/serena_analysis.py \
  server/api.py \
  server/claude_runner.py \
  server/hypothesis_store.py \
  server/hypothesis_cycle.py
run npm --prefix frontend ci
run npm --prefix frontend run lint
run npm --prefix frontend test
run npm --prefix frontend run build
run npm --prefix frontend run test:browser
run git diff --check
