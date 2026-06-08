FROM python:3.12-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_INDEX_URL=https://mirror.yandex.ru/mirrors/pypi/simple/

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PREFER_BINARY=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_EXTRA_INDEX_URL=${PIP_EXTRA_INDEX_URL}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bootstrap без сети (setuptools/wheel/certifi).
COPY packages/kb/docker/bootstrap-wheels/ /tmp/bootstrap-wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/bootstrap-wheels \
    setuptools wheel certifi \
    && rm -rf /tmp/bootstrap-wheels

# Только зависимости MCP (без Flask из корневого pyproject).
COPY packages/kb/docker/requirements-kb-mcp.txt /tmp/requirements-kb-mcp.txt
COPY packages/kb/docker/install-kb-deps.sh /tmp/install-kb-deps.sh
RUN chmod +x /tmp/install-kb-deps.sh && /tmp/install-kb-deps.sh && rm -f /tmp/install-kb-deps.sh

COPY pyproject.toml README.md ./
COPY packages ./packages

# Пакет monorepo без повторной установки зависимостей (entry point 1c-cursor-kb-mcp).
RUN pip install --no-cache-dir --no-deps --no-build-isolation -e .

ENV HF_HOME=/app/data/hf_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY packages/kb/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
