"""Smoke-тесты MCP tools."""

from __future__ import annotations

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.mcp_server.server import get_config, get_mcp


@pytest.fixture
def mcp_server(fixture_profile_config, monkeypatch):
    from packages.kb import indexer as config_mod  # noqa: F401 — fixture side effect

    cfg = load_config(fixture_profile_config)
    monkeypatch.setattr("packages.kb.mcp_server.server._config", cfg)
    monkeypatch.setattr("packages.kb.mcp_server.server._mcp", None)
    return get_mcp()


def test_mcp_registers_eight_tools(mcp_server):
    tools = mcp_server._tool_manager.list_tools()
    names = sorted(t.name for t in tools)
    expected = sorted([
        "search_project",
        "get_object",
        "get_module_summary",
        "list_subsystems",
        "find_references",
        "list_object_modules",
        "search_by_subsystem",
        "get_register_movements",
    ])
    assert names == expected


def test_search_project_tool(mcp_server, fixture_profile_config, monkeypatch):
    from packages.kb.indexer.pipeline import run_index
    from packages.kb.indexer.store import reset_store_cache
    import packages.kb.mcp_server.server as srv

    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)

    monkeypatch.setattr(srv, "_config", config)
    tool = mcp_server._tool_manager.get_tool("search_project")
    result = tool.fn(query="ТестовыйДокумент", limit=3, hybrid=False)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.fixture
def indexed_mcp(mcp_server, fixture_profile_config, monkeypatch):
    from packages.kb.indexer.pipeline import run_index
    from packages.kb.indexer.store import reset_store_cache
    import packages.kb.mcp_server.server as srv

    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)
    monkeypatch.setattr(srv, "_config", config)
    return mcp_server, config


def test_get_object_tool(indexed_mcp):
    mcp_server, config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_object")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент")
    assert "ТестовыйДокумент" in result


def test_list_object_modules_tool(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("list_object_modules")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент")
    assert "ObjectModule" in result or "Модули" in result


def test_find_references_tool(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("find_references")
    result = tool.fn(identifier="Проведение", limit=5)
    assert isinstance(result, str)


def test_get_module_summary_tool(indexed_mcp, fixture_profile_config):
    mcp_server, config = indexed_mcp
    from packages.kb.indexer.scanner import scan_profile
    from packages.kb.indexer.models import FileKind

    bsl_path = next(
        e.path for e in scan_profile(config) if e.kind == FileKind.BSL
    )
    tool = mcp_server._tool_manager.get_tool("get_module_summary")
    result = tool.fn(module_path=str(bsl_path))
    assert "Проведение" in result or "Модуль" in result


def test_get_register_movements_tool(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_register_movements")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент")
    assert isinstance(result, str)
    assert "ТестовыйРегистр" in result or "не найден" in result.lower()


def test_list_subsystems_empty_index(mcp_server):
    tool = mcp_server._tool_manager.get_tool("list_subsystems")
    result = tool.fn(subsystem_name="")
    assert isinstance(result, str)
