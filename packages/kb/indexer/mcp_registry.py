from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.docker_manager import mcp_entry_for_profile, mcp_url


def parse_mcp_json(content: str | bytes) -> dict[str, Any]:
    data = json.loads(content)
    if not isinstance(data, dict):
        raise ValueError("Корень mcp.json должен быть объектом")
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    if not isinstance(data["mcpServers"], dict):
        raise ValueError("mcpServers должен быть объектом")
    return data


def merge_server(
    mcp_data: dict[str, Any],
    config: ProfileConfig,
    host_port: int | None = None,
    *,
    overwrite: bool = True,
) -> dict[str, Any]:
    server_name = config.mcp.server_name
    entry = mcp_entry_for_profile(config, host_port)
    servers = mcp_data.setdefault("mcpServers", {})
    if server_name in servers and not overwrite:
        raise ValueError(f"Сервер '{server_name}' уже есть в mcp.json")
    servers[server_name] = entry
    return mcp_data


def format_mcp_json(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def build_standalone_entry(config: ProfileConfig, host_port: int | None = None) -> dict[str, Any]:
    return {
        "mcpServers": {
            config.mcp.server_name: mcp_entry_for_profile(config, host_port),
        }
    }


def cursor_instructions(config: ProfileConfig, host_port: int | None = None) -> str:
    port = host_port or config.mcp.port
    url = mcp_url(port)
    return (
        f"1. Убедитесь, что контейнер MCP запущен (порт {port})\n"
        f"2. Загрузите свой mcp.json или скачайте готовый фрагмент\n"
        f"3. В Cursor: Settings → MCP — проверьте сервер `{config.mcp.server_name}`\n"
        f"4. URL сервера: {url}"
    )
