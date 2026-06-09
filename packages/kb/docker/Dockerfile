# KB MCP — единый образ для всех профилей (KB_PROFILE в runtime).
FROM python:3.12-slim

WORKDIR /app

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=pypi.org

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PREFER_BINARY=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bootstrap pip (малые пакеты; основные deps — офлайн из wheels на хосте).
RUN pip install --no-cache-dir setuptools wheel certifi \
    --index-url "${PIP_INDEX_URL}" \
    --trusted-host "${PIP_TRUSTED_HOST}"

COPY packages/kb/docker/wheels-kb-mcp/ /tmp/wheels-kb-mcp/
COPY packages/kb/docker/requirements-kb-mcp.txt /tmp/requirements-kb-mcp.txt
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels-kb-mcp \
    -r /tmp/requirements-kb-mcp.txt \
    && rm -rf /tmp/wheels-kb-mcp

COPY pyproject.toml README.md ./
COPY packages ./packages

RUN pip install --no-cache-dir --no-deps --no-build-isolation -e .

ENV HF_HOME=/app/data/hf_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', 8000)); s.close()"

COPY packages/kb/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
