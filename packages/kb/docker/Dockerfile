FROM python:3.12-slim

WORKDIR /app

# Медленный/нестабильный PyPI: дефолтный timeout pip (15 с) часто рвёт сборку на setuptools.
ENV PIP_DEFAULT_TIMEOUT=300 \
    PIP_RETRIES=10 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

ARG PIP_INDEX_URL=
ARG PIP_TRUSTED_HOST=
ENV PIP_INDEX_URL=${PIP_INDEX_URL} \
    PIP_TRUSTED_HOST=${PIP_TRUSTED_HOST}

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Отдельный слой: кэшируется; editable install не качает build-deps заново.
RUN pip install --no-cache-dir --upgrade pip "setuptools>=68" wheel

COPY pyproject.toml README.md ./
COPY packages ./packages

RUN pip install --no-cache-dir -e ".[kb]"

ENV HF_HOME=/app/data/hf_cache
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

COPY packages/kb/docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
