from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.docker_manager import mcp_url


class CursorMcpStatus(str, Enum):
    MISSING = "missing"
    MISCONFIGURED = "misconfigured"
    CONFIGURED = "configured"
    READY = "ready"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class CursorMcpState:
    status: CursorMcpStatus
    message: str
    in_mcp_json: bool = False
    url_matches: bool = False
    mcp_json_url: str = ""
    expected_url: str = ""
    mcp_reachable: bool = False
    cursor_tools_count: int = 0
    mcp_json_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "message": self.message,
            "in_mcp_json": self.in_mcp_json,
            "url_matches": self.url_matches,
            "mcp_json_url": self.mcp_json_url,
            "expected_url": self.expected_url,
            "mcp_reachable": self.mcp_reachable,
            "cursor_tools_count": self.cursor_tools_count,
            "mcp_json_path": self.mcp_json_path,
        }


def cursor_mcp_json_path() -> Path:
    from packages.kb.indexer.cursor_mcp_config import cursor_mcp_json_path_resolved

    try:
        return cursor_mcp_json_path_resolved()
    except ValueError:
        return Path.home() / ".cursor" / "mcp.json"


def cursor_mcp_server_dir(server_name: str) -> str:
    return f"user-{server_name}"


def normalize_mcp_url(url: str) -> str:
    value = (url or "").strip()
    if not value:
        return ""
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower()
    if host == "localhost":
        host = "127.0.0.1"
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    path = parsed.path.rstrip("/") or "/mcp"
    return urlunparse((parsed.scheme.lower(), f"{host}:{port}", path, "", "", ""))


def read_cursor_mcp_json() -> dict[str, Any] | None:
    from packages.kb.indexer.cursor_mcp_config import resolve_cursor_config_dir

    try:
        path = resolve_cursor_config_dir() / "mcp.json"
    except ValueError:
        return None
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        return None
    return data


def get_server_entry(server_name: str) -> tuple[dict[str, Any] | None, str]:
    data = read_cursor_mcp_json()
    if not data:
        return None, ""
    entry = data.get("mcpServers", {}).get(server_name)
    if not isinstance(entry, dict):
        return None, ""
    url = str(entry.get("url") or "").strip()
    return entry, url


def count_cursor_tools(server_name: str) -> int:
    projects_dir = Path.home() / ".cursor" / "projects"
    if not projects_dir.exists():
        return 0

    server_dir = cursor_mcp_server_dir(server_name)
    best = 0
    for project in projects_dir.iterdir():
        if not project.is_dir():
            continue
        tools_dir = project / "mcps" / server_dir / "tools"
        if not tools_dir.is_dir():
            continue
        count = sum(1 for item in tools_dir.glob("*.json") if item.is_file())
        best = max(best, count)
    return best


def probe_mcp_http(url: str, *, timeout: float = 4.0) -> tuple[bool, str]:
    normalized = normalize_mcp_url(url)
    if not normalized:
        return False, "URL не задан"

    payload = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "kb-web", "version": "1"},
            },
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        normalized,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        snippet = exc.read(512).decode("utf-8", errors="replace")
        return False, f"HTTP {exc.code}: {snippet[:160]}"
    except Exception as exc:
        return False, str(exc)

    if '"result"' in body and "serverInfo" in body:
        return True, "MCP отвечает на initialize"
    if "error" in body:
        return False, body[:200]
    return False, "Неожиданный ответ MCP"


def get_cursor_mcp_status(
    config: ProfileConfig,
    host_port: int | None = None,
    *,
    docker_running: bool = False,
    probe: bool = True,
) -> CursorMcpState:
    from packages.kb.indexer.cursor_mcp_config import cursor_settings_summary

    expected_url = mcp_url(host_port or config.mcp.port)
    server_name = config.mcp.server_name
    cursor_cfg = cursor_settings_summary()
    mcp_json_path = cursor_cfg.get("mcp_json_path") or str(cursor_mcp_json_path())

    if not cursor_cfg.get("cursor_dir_ready"):
        return CursorMcpState(
            status=CursorMcpStatus.MISSING,
            message=cursor_cfg.get("cursor_dir_error")
            or "Укажите каталог конфигурации Cursor",
            in_mcp_json=False,
            expected_url=expected_url,
            mcp_json_path=mcp_json_path,
        )

    entry, configured_url = get_server_entry(server_name)
    in_mcp_json = entry is not None
    url_matches = bool(
        configured_url
        and normalize_mcp_url(configured_url) == normalize_mcp_url(expected_url)
    )
    tools_count = count_cursor_tools(server_name)
    reachable = False
    reach_message = ""

    if probe and in_mcp_json and entry and entry.get("url"):
        reachable, reach_message = probe_mcp_http(str(entry["url"]))
    elif probe and docker_running:
        reachable, reach_message = probe_mcp_http(expected_url)

    if (
        tools_count > 0
        and in_mcp_json
        and url_matches
        and docker_running
        and reachable
    ):
        return CursorMcpState(
            status=CursorMcpStatus.CONNECTED,
            message=f"Cursor загрузил {tools_count} инструмент(ов) — сервер включён",
            in_mcp_json=True,
            url_matches=True,
            mcp_json_url=configured_url,
            expected_url=expected_url,
            mcp_reachable=reachable,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if in_mcp_json and url_matches and not docker_running:
        return CursorMcpState(
            status=CursorMcpStatus.CONFIGURED,
            message=(
                f"В mcp.json есть «{server_name}», но контейнер профиля не запущен. "
                "Сначала выполните шаг 2 (Docker)"
            ),
            in_mcp_json=True,
            url_matches=url_matches,
            mcp_json_url=configured_url,
            expected_url=expected_url,
            mcp_reachable=reachable,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if in_mcp_json and url_matches and reachable:
        return CursorMcpState(
            status=CursorMcpStatus.READY,
            message="Сервер в mcp.json и отвечает. В Cursor: Settings → MCP — включите переключатель",
            in_mcp_json=True,
            url_matches=True,
            mcp_json_url=configured_url,
            expected_url=expected_url,
            mcp_reachable=True,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if in_mcp_json and not url_matches:
        return CursorMcpState(
            status=CursorMcpStatus.MISCONFIGURED,
            message=(
                f"В mcp.json другой URL: {configured_url or '—'}. "
                f"Ожидается: {expected_url}"
            ),
            in_mcp_json=True,
            url_matches=False,
            mcp_json_url=configured_url,
            expected_url=expected_url,
            mcp_reachable=reachable,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if in_mcp_json:
        return CursorMcpState(
            status=CursorMcpStatus.CONFIGURED,
            message=(
                "Запись в mcp.json есть, но MCP недоступен. "
                "Запустите Docker-контейнер и проверьте URL"
            ),
            in_mcp_json=True,
            url_matches=url_matches,
            mcp_json_url=configured_url,
            expected_url=expected_url,
            mcp_reachable=reachable,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if docker_running and reachable:
        return CursorMcpState(
            status=CursorMcpStatus.CONFIGURED,
            message="MCP работает, но сервер ещё не добавлен в ~/.cursor/mcp.json",
            in_mcp_json=False,
            url_matches=False,
            expected_url=expected_url,
            mcp_reachable=True,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    if docker_running and not reachable:
        return CursorMcpState(
            status=CursorMcpStatus.ERROR,
            message=f"Контейнер запущен, но MCP не отвечает: {reach_message}",
            in_mcp_json=False,
            expected_url=expected_url,
            mcp_reachable=False,
            cursor_tools_count=tools_count,
            mcp_json_path=mcp_json_path,
        )

    return CursorMcpState(
        status=CursorMcpStatus.MISSING,
        message="Добавьте сервер в mcp.json и запустите контейнер",
        in_mcp_json=False,
        expected_url=expected_url,
        mcp_reachable=False,
        cursor_tools_count=tools_count,
        mcp_json_path=mcp_json_path,
    )
