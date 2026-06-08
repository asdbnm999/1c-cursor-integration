#!/bin/sh
# Установка зависимостей KB MCP: PyPI → запасное зеркало при сбое сети.
set -e

REQS="/tmp/requirements-kb-mcp.txt"
PRIMARY_INDEX="${PIP_INDEX_URL:-https://pypi.org/simple}"
EXTRA_INDEX="${PIP_EXTRA_INDEX_URL:-https://mirror.yandex.ru/mirrors/pypi/simple/}"

pip_install() {
  pip install --no-cache-dir --prefer-binary "$@"
}

if pip_install \
  --index-url "$PRIMARY_INDEX" \
  --extra-index-url "$EXTRA_INDEX" \
  --trusted-host pypi.org \
  --trusted-host files.pythonhosted.org \
  --trusted-host mirror.yandex.ru \
  -r "$REQS"; then
  exit 0
fi

echo "WARN: primary PyPI failed, retrying mirror only..." >&2
pip_install \
  --index-url "$EXTRA_INDEX" \
  --trusted-host mirror.yandex.ru \
  -r "$REQS"
