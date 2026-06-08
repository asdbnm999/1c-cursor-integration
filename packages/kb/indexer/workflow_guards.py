from __future__ import annotations

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.docker_manager import get_status as docker_status
from packages.kb.indexer.store import count_chunks


def profile_chunks(config: ProfileConfig) -> int:
    try:
        return count_chunks(config)
    except Exception:
        return 0


def require_indexed_profile(name: str) -> int:
    config = load_config(name)
    chunks = profile_chunks(config)
    if chunks <= 0:
        raise ValueError("Сначала выполните полную индексацию")
    return chunks


def container_created(name: str) -> bool:
    return bool(docker_status(name).container_id)


def require_container_for_mcp(name: str) -> None:
    if not container_created(name):
        raise ValueError("Сначала соберите образ и запустите контейнер")
