from __future__ import annotations

import os
import shutil
import threading
from pathlib import Path
from typing import Any

import chromadb

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.exceptions import StoreError
from packages.kb.indexer.models import Chunk

_client: chromadb.ClientAPI | None = None
_client_key: str | None = None
_collection: chromadb.Collection | None = None
_collection_key: str | None = None
_store_lock = threading.RLock()


def _release_client() -> None:
    """Закрыть SQLite-соединения Chroma перед сбросом каталога."""
    global _client
    if _client is None:
        return
    try:
        close = getattr(_client, "close", None)
        if callable(close):
            close()
    except Exception:
        pass
    _client = None


def _resolve_store_path(config: ProfileConfig) -> Path:
    store_path = Path(config.store.path)
    if not store_path.is_absolute():
        store_path = config.project_root / store_path
    store_path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(store_path, 0o755)
    except OSError:
        pass
    return store_path


def get_client(config: ProfileConfig) -> chromadb.ClientAPI:
    global _client, _client_key
    key = str(_resolve_store_path(config))
    with _store_lock:
        if _client is None or _client_key != key:
            _release_client()
            _client = chromadb.PersistentClient(path=key)
            _client_key = key
            global _collection, _collection_key
            _collection = None
            _collection_key = None
        return _client


def get_collection(config: ProfileConfig, reset: bool = False) -> chromadb.Collection:
    global _collection, _collection_key
    with _store_lock:
        client = get_client(config)
        key = f"{_resolve_store_path(config)}::{config.store.collection}"
        if reset:
            try:
                client.delete_collection(config.store.collection)
            except Exception:
                pass
            _collection = None
        if _collection is None or _collection_key != key:
            _collection = client.get_or_create_collection(
                name=config.store.collection,
                metadata={"hnsw:space": "cosine"},
            )
            _collection_key = key
        return _collection


def reset_store_cache() -> None:
    global _client_key, _collection, _collection_key
    with _store_lock:
        _release_client()
        _client_key = None
        _collection = None
        _collection_key = None


def reset_collection_store(config: ProfileConfig) -> chromadb.Collection:
    """Полный сброс каталога Chroma (полная индексация)."""
    store_path = _resolve_store_path(config)
    with _store_lock:
        reset_store_cache()
        if store_path.exists():
            shutil.rmtree(store_path)
        store_path.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(store_path, 0o755)
        except OSError:
            pass
        client = chromadb.PersistentClient(path=str(store_path))
        global _client, _client_key, _collection, _collection_key
        _client = client
        _client_key = str(store_path)
        _collection = client.get_or_create_collection(
            name=config.store.collection,
            metadata={"hnsw:space": "cosine"},
        )
        _collection_key = f"{store_path}::{config.store.collection}"
        return _collection


def _sanitize_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, bool):
            result[key] = value
        elif isinstance(value, (int, float)):
            result[key] = value
        else:
            result[key] = str(value)
    return result


def upsert_chunks(config: ProfileConfig, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    if any(chunk.embedding is None for chunk in chunks):
        raise StoreError("Все чанки должны иметь embedding перед upsert")
    try:
        with _store_lock:
            collection = get_collection(config)
            collection.upsert(
                ids=[chunk.id for chunk in chunks],
                documents=[chunk.text for chunk in chunks],
                metadatas=[_sanitize_metadata(chunk.metadata) for chunk in chunks],
                embeddings=[chunk.embedding for chunk in chunks],
            )
    except Exception as exc:
        raise StoreError("Ошибка записи в Chroma", details=str(exc)) from exc


def delete_by_path(config: ProfileConfig, path: str) -> int:
    with _store_lock:
        collection = get_collection(config)
        try:
            existing = collection.get(where={"path": path}, include=[])
            ids = existing.get("ids", [])
            if ids:
                collection.delete(ids=ids)
            return len(ids)
        except Exception:
            return 0


def path_has_chunks(config: ProfileConfig, path: str) -> bool:
    norm = str(Path(path).expanduser().resolve())
    with _store_lock:
        collection = get_collection(config)
        for candidate in (norm, path):
            try:
                existing = collection.get(where={"path": candidate}, include=[])
                if existing.get("ids"):
                    return True
            except Exception:
                continue
    return False


def count_chunks(config: ProfileConfig, *, force: bool = False) -> int:
    if not force:
        from packages.kb.indexer.jobs import JobStatus, get_profile_job

        job = get_profile_job(config.profile_name)
        if job and job.status in {JobStatus.PENDING, JobStatus.RUNNING}:
            return int((job.progress or {}).get("chunks_written") or 0)
    with _store_lock:
        return get_collection(config).count()


def query_chunks(
    config: ProfileConfig,
    embedding: list[float],
    limit: int = 8,
    where: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _store_lock:
        collection = get_collection(config)
        kwargs: dict[str, Any] = {
            "query_embeddings": [embedding],
            "n_results": limit,
            "include": ["documents", "metadatas", "distances"],
        }
        if where:
            kwargs["where"] = where
        return collection.query(**kwargs)


def get_by_metadata(config: ProfileConfig, where: dict[str, Any]) -> dict[str, Any]:
    with _store_lock:
        collection = get_collection(config)
        return collection.get(where=where, include=["documents", "metadatas"])
