"""Константы §2: серверы, порты, пресеты ресурсов (ТЗ §7, §10, §20.A)."""

from __future__ import annotations

from typing import Any

SEARXNG_SLUG = "searxng"
SYNTAX_SLUG = "1c-syntax-helper"

SEARXNG_MCP_KEY = "searxng"
SYNTAX_MCP_KEY = "1c-syntax-helper"

DEFAULT_PORT_SEARXNG_MCP = 8201
DEFAULT_PORT_SEARXNG_CORE = 8202
DEFAULT_PORT_SYNTAX_MCP = 8203

SYNTAX_REPO_URL = "https://github.com/Antonio1C/1c-syntax-helper-mcp.git"
SYNTAX_REPO_DIRNAME = "1c-syntax-helper-mcp"

RESOURCE_LIMITS_UI = {
    "valkey_mem": {"min": 64, "max": 512, "unit": "m"},
    "core_mem": {"min": 256, "max": 1536, "unit": "m"},
    "searxng_mcp_mem": {"min": 128, "max": 1024, "unit": "m"},
    "es_heap": {"min": 256, "max": 2048, "unit": "m"},
    "syntax_mcp_mem": {"min": 256, "max": 2048, "unit": "m"},
}

RESOURCE_PRESETS: dict[str, dict[str, int]] = {
    "economical": {
        "valkey_mem": 128,
        "core_mem": 384,
        "searxng_mcp_mem": 256,
        "es_heap": 512,
        "es_mem": 1024,
        "syntax_mcp_mem": 512,
    },
    "extended": {
        "valkey_mem": 256,
        "core_mem": 768,
        "searxng_mcp_mem": 512,
        "es_heap": 1024,
        "es_mem": 2048,
        "syntax_mcp_mem": 1024,
    },
}

SERVER_UI: dict[str, dict[str, str]] = {
    SEARXNG_SLUG: {
        "title": "SearXNG",
        "mcp_key": SEARXNG_MCP_KEY,
        "why": (
            "Локальный веб-поиск без API-ключей. AI ищет статьи Infostart, документацию "
            "и релизы через ваш SearXNG — весь web search только через MCP, не через "
            "встроенный поиск Cursor."
        ),
        "tools": "searxng_web_search, web_url_read",
    },
    SYNTAX_SLUG: {
        "title": "1C Syntax Helper",
        "mcp_key": SYNTAX_MCP_KEY,
        "why": (
            "Справка платформы 1С из вашего shcntx_ru.hbk. AI проверяет методы и параметры "
            "после написания кода — меньше выдуманных API."
        ),
        "tools": (
            "find_1c_help, get_syntax_info, get_quick_reference, search_by_context, "
            "list_object_members"
        ),
    },
}

EXTERNAL_VOLUMES = {
    "searxng_core": "dockermcp_core-data",
    "syntax_es": "dockermcp_es-1c-data",
}


def default_server_settings(slug: str) -> dict[str, Any]:
    if slug == SEARXNG_SLUG:
        return {
            "enabled": False,
            "slug": SEARXNG_SLUG,
            "compose_dir": "",
            "host_port_mcp": DEFAULT_PORT_SEARXNG_MCP,
            "host_port_mcp_manual": False,
            "host_port_core": DEFAULT_PORT_SEARXNG_CORE,
            "secret_key": "",
            "resource_preset": "economical",
            "resources": dict(RESOURCE_PRESETS["economical"]),
            "use_external_volumes": True,
            "deployed": False,
        }
    if slug == SYNTAX_SLUG:
        return {
            "enabled": False,
            "slug": SYNTAX_SLUG,
            "compose_dir": "",
            "host_port_mcp": DEFAULT_PORT_SYNTAX_MCP,
            "host_port_mcp_manual": False,
            "hbk_path": "",
            "resource_preset": "economical",
            "resources": dict(RESOURCE_PRESETS["economical"]),
            "use_external_volumes": True,
            "deployed": False,
        }
    raise ValueError(f"Неизвестный сервер: {slug}")
