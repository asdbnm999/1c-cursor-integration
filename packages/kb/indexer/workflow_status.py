from __future__ import annotations

from typing import Any

from packages.kb.indexer.docker_build import image_exists


def compute_workflow_status(
    *,
    profile_name: str,
    chunks: int,
    index_job: dict[str, Any] | None,
    docker_running: bool,
    cursor_mcp: dict[str, Any],
) -> dict[str, Any]:
    """Четыре шага полного цикла профиля для главной страницы."""

    job_status = (index_job or {}).get("status")
    index_done = chunks > 0 and job_status not in ("running", "failed", "pending")
    image_done = image_exists(profile_name)
    container_done = docker_running
    cursor_done = cursor_mcp.get("status") == "connected"

    steps = {
        "index": index_done,
        "docker_image": image_done,
        "docker_running": container_done,
        "cursor": cursor_done,
    }
    completed = sum(1 for value in steps.values() if value)

    labels = {
        "index": "Индексация",
        "docker_image": "Образ Docker",
        "docker_running": "Контейнер",
        "cursor": "Cursor MCP",
    }

    return {
        "steps": steps,
        "step_labels": labels,
        "completed_count": completed,
        "total_count": 4,
        "all_complete": completed == 4,
    }
