#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if ! command -v uv >/dev/null; then
  echo 'Install uv, or use Python 3.10+ with python -m venv .venv and pip install -e ".[test]".' >&2
  exit 1
fi
if [[ ! -d .venv ]]; then uv venv .venv; fi
uv pip install --python .venv/bin/python -e '.[test]'
npm ci
