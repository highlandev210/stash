#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ ! -x .venv/bin/uvicorn ]]; then
  echo 'Run bash scripts/setup.sh first to install the Python backend.' >&2
  exit 1
fi
npm run dev:api &
api_pid=$!
npm run dev &
web_pid=$!
trap 'kill "$api_pid" "$web_pid" 2>/dev/null || true; wait 2>/dev/null || true' EXIT INT TERM
wait -n "$api_pid" "$web_pid"
