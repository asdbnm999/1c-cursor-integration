"""Шаблон имён Docker MCP-стеков (ТЗ §7.2)."""

from __future__ import annotations


def mcp_stack_name(slug: str) -> str:
    """slug → '{slug}-mcp' для project/service/container MCP-endpoint."""
    return f"{slug.strip()}-mcp"


def auxiliary_name(slug: str, role: str) -> str:
    """→ '{slug}-mcp-{role}' для valkey/core/es."""
    return f"{slug.strip()}-mcp-{role}"


def mcp_json_key(slug: str) -> str:
    """Ключ в mcp.json без суффикса -mcp."""
    name = slug.strip()
    if name.endswith("-mcp"):
        return name[:-4]
    return name
