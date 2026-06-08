from __future__ import annotations

CONTAINER_PREFIX = "1c-kb-"
CONTAINER_PORT = 8000


def container_name(profile_name: str) -> str:
    return f"{CONTAINER_PREFIX}{profile_name}-mcp"


def image_name(profile_name: str) -> str:
    """Имя образа совпадает с именем контейнера."""
    return container_name(profile_name)
