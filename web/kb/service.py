"""Статус раздела §3 KB для dashboard (ТЗ §6.4)."""

from __future__ import annotations

from packages.kb.indexer.config import load_config
from packages.kb.indexer.cursor_mcp_status import get_cursor_mcp_status
from packages.kb.indexer.docker_manager import get_status as docker_status
from packages.kb.indexer.health import health_for_profile
from packages.kb.indexer.profiles import list_profiles
from packages.kb.indexer.store import count_chunks
from packages.kb.indexer.workflow_status import compute_workflow_status
from web.cursor_mcp import read_mcp_config


def compute_kb_section_status() -> str:
    """
    ready — ≥1 профиль ready + контейнер + MCP в конфиге (§6.4).
    in_progress — есть профили, но условие не выполнено.
    not_started — нет профилей.
    """
    profiles = list_profiles()
    if not profiles:
        return "not_started"

    mcp_servers = read_mcp_config().get("mcpServers", {})
    any_ready = False
    any_activity = False

    for name in profiles:
        try:
            config = load_config(name)
            chunks = count_chunks(config)
        except Exception:
            chunks = 0
        container = docker_status(name)
        if chunks > 0 or container.running:
            any_activity = True

        try:
            health = health_for_profile(name)
            workflow = compute_workflow_status(
                profile_name=name,
                chunks=chunks,
                index_job=None,
                docker_running=container.running,
                cursor_mcp=get_cursor_mcp_status(
                    config,
                    container.host_port or config.mcp.port,
                    docker_running=container.running,
                ).to_dict(),
            )
        except Exception:
            continue

        server_key = config.mcp.server_name
        in_mcp = server_key in mcp_servers
        if health.get("state") == "ready" and container.running and in_mcp:
            any_ready = True

    if any_ready:
        return "ready"
    if any_activity or profiles:
        return "in_progress"
    return "not_started"


def update_kb_section_status_in_settings() -> str:
    """Сохранить вычисленный статус §3 в settings.sections.kb."""
    status = compute_kb_section_status()
    from web.settings import load_settings, save_settings

    settings = load_settings()
    sections = settings.setdefault("sections", {})
    if sections.get("kb") != status:
        sections["kb"] = status
        save_settings(settings)
    return status
