FROM python:3.12-slim

WORKDIR /app

# Зеркало PyPI по умолчанию (без ручной настройки). Переопределение: --build-arg PIP_INDEX_URL=...
ARG PIP_INDEX_URL=https://mirror.yandex.ru/mirrors/pypi/simple/
ARG PIP_TRUSTED_HOST=mirror.yandex.ru

ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PREFER_BINARY=1 \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Bootstrap без сети: setuptools/wheel/certifi из репозитория (обход SSL к PyPI на первом шаге).
COPY packages/kb/docker/bootstrap-wheels/ /tmp/bootstrap-wheels/
RUN pip install --no-cache-dir --no-index --find-links=/tmp/bootstrap-wheels \
    setuptools wheel certifi \
    && rm -rf /tmp/bootstrap-wheels

COPY pyproject.toml README.md ./
COPY packages ./packages

RUN pip install --no-cache-dir --no-build-isolation --prefer-binary -e ".[kb]"

ENV HF_HOME=/app/data/hf_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY packages/kb/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
