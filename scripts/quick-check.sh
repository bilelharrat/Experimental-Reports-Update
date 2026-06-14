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

if [ "$#" -gt 0 ]; then
  run python -m pytest "$@"
fi

run npm --prefix frontend test
run git diff --check
