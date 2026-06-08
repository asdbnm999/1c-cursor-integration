#!/usr/bin/env python3
"""Регистрация MCP-сервера профиля в ~/.cursor/mcp.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.kb.indexer.config import load_config  # noqa: E402
from packages.kb.indexer.profiles import list_profiles  # noqa: E402

MCP_JSON = Path.home() / ".cursor" / "mcp.json"


def _python_command() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _stdio_entry(profile_name: str) -> dict:
    return {
        "command": _python_command(),
        "args": ["-m", "mcp_server.server", "--profile", profile_name],
        "cwd": str(ROOT),
    }


def _http_entry(config) -> dict:
    return {"url": f"http://{config.mcp.host}:{config.mcp.port}/mcp"}


def load_mcp_json() -> dict:
    if not MCP_JSON.exists():
        return {"mcpServers": {}}
    with MCP_JSON.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    return data


def save_mcp_json(data: dict) -> None:
    MCP_JSON.parent.mkdir(parents=True, exist_ok=True)
    with MCP_JSON.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Зарегистрировать MCP в Cursor")
    parser.add_argument("--profile", "-p", required=True)
    parser.add_argument("--remove", action="store_true", help="Удалить сервер из mcp.json")
    parser.add_argument("--dry-run", action="store_true", help="Показать без записи")
    parser.add_argument("--list", action="store_true", help="Список профилей")
    args = parser.parse_args()

    if args.list:
        for name in list_profiles():
            print(name)
        return

    config = load_config(args.profile)
    server_name = config.mcp.server_name
    data = load_mcp_json()

    if args.remove:
        if server_name in data["mcpServers"]:
            del data["mcpServers"][server_name]
            action = f"Удалён: {server_name}"
        else:
            print(f"Сервер не найден: {server_name}")
            sys.exit(0)
    else:
        entry = _http_entry(config) if config.mcp.transport == "http" else _stdio_entry(config.profile_name)
        data["mcpServers"][server_name] = entry
        action = f"Зарегистрирован: {server_name}"

    if args.dry_run:
        print(json.dumps({server_name: data["mcpServers"].get(server_name)}, indent=2, ensure_ascii=False))
        return

    save_mcp_json(data)
    print(action)
    print(f"Файл: {MCP_JSON}")
    print("Перезапустите MCP в Cursor: Settings → MCP")


if __name__ == "__main__":
    main()
