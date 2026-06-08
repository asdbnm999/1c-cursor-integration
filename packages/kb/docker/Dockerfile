FROM python:3.12-slim

WORKDIR /app

# Нестабильный PyPI / SSL: увеличенный timeout и retries.
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_PREFER_BINARY=1

ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# pip из python:3.12-slim достаточен. --upgrade pip часто падает по SSL (запрос к /simple/pip/).
RUN pip install --no-cache-dir "setuptools>=68" wheel certifi

COPY pyproject.toml README.md ./
COPY packages ./packages

RUN pip install --no-cache-dir --no-build-isolation --prefer-binary -e ".[kb]"

ENV HF_HOME=/app/data/hf_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY packages/kb/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
