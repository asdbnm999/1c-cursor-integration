from __future__ import annotations

CONTAINER_PREFIX = "1c-kb-"
CONTAINER_PORT = 8000

# Единый образ MCP для всех профилей (ТЗ §11.8 — допускается общий образ).
SHARED_IMAGE_NAME = "1c-kb-mcp:latest"


def container_name(profile_name: str) -> str:
    return f"{CONTAINER_PREFIX}{profile_name}-mcp"


def image_name(profile_name: str) -> str:
    """Тег образа профиля (alias общего образа после сборки)."""
    return container_name(profile_name)
