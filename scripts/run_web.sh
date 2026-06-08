#!/usr/bin/env bash
# Запуск веб-UI 1C:Cursor (из корня репозитория).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
if [[ -x "$ROOT/.venv/bin/1c-cursor-web" ]]; then
  exec "$ROOT/.venv/bin/1c-cursor-web" "$@"
fi
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  exec "$ROOT/.venv/bin/python" -m web.app "$@"
fi
exec python3 -m web.app "$@"
