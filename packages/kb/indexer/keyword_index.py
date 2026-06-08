"""Построение и чтение keyword-индекса для гибридного поиска."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.models import Chunk

logger = logging.getLogger(__name__)

INDEX_VERSION = 1


def keyword_index_path(config: ProfileConfig) -> Path:
    return config.project_root / "data" / "profiles" / config.profile_name / "indexes" / "keyword" / "index.json"


def build_keyword_index(config: ProfileConfig, chunks: list[Chunk]) -> Path:
    """Сохраняет документы чанков для BM25-поиска."""
    path = keyword_index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    documents = [
        {
            "id": chunk.id,
            "text": chunk.text,
            "metadata": chunk.metadata,
        }
        for chunk in chunks
    ]
    payload = {
        "version": INDEX_VERSION,
        "profile": config.profile_name,
        "collection": config.store.collection,
        "documents": documents,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    logger.info("Keyword index: %d документов → %s", len(documents), path)
    return path


def merge_keyword_index(
    config: ProfileConfig,
    chunks: list[Chunk],
    *,
    deleted_paths: list[str] | None = None,
) -> Path:
    """Обновляет keyword index: удаляет чанки удалённых файлов, добавляет новые."""
    existing = load_keyword_documents(config)
    deleted_set = {str(p) for p in (deleted_paths or [])}
    kept = [
        doc for doc in existing
        if doc.get("metadata", {}).get("path") not in deleted_set
    ]
    by_id = {doc["id"]: doc for doc in kept}
    for chunk in chunks:
        if chunk.embedding:
            by_id[chunk.id] = {
                "id": chunk.id,
                "text": chunk.text,
                "metadata": chunk.metadata,
            }
    path = keyword_index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": INDEX_VERSION,
        "profile": config.profile_name,
        "collection": config.store.collection,
        "documents": list(by_id.values()),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def load_keyword_documents(config: ProfileConfig) -> list[dict[str, Any]]:
    path = keyword_index_path(config)
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("documents") or [])
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Не удалось прочитать keyword index: %s", exc)
        return []
