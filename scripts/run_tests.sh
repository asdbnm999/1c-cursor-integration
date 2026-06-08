#!/usr/bin/env bash
# Полный прогон тестов 1C:Cursor (шаг 8, ТЗ §15)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

pip install -q -e ".[kb,dev]"
pytest tests/ -v --tb=short "$@"
