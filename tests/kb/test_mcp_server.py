"""Smoke-тесты MCP tools."""

from __future__ import annotations

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.mcp_server.server import MCP_TOOLS, get_config, get_mcp


@pytest.fixture
def mcp_server(fixture_profile_config, monkeypatch):
    cfg = load_config(fixture_profile_config)
    monkeypatch.setattr("packages.kb.mcp_server.server._config", cfg)
    monkeypatch.setattr("packages.kb.mcp_server.server._mcp", None)
    return get_mcp()


def test_mcp_registers_five_tools(mcp_server):
    tools = mcp_server._tool_manager.list_tools()
    names = sorted(t.name for t in tools)
    assert names == sorted(MCP_TOOLS)


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
    assert "Тип совпадения:" in result


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


def test_get_object_brief(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_object")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент", detail="brief")
    assert "ТестовыйДокумент" in result


def test_get_object_movements(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_object")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент", detail="movements")
    assert "ТестовыйРегистр" in result
    assert "Расход" in result
    assert "ОбработкаПроведения" in result


def test_get_object_structure(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_object")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент", detail="structure")
    assert "RegisterRecords" in result
    assert "Сумма" in result


def test_get_object_posting(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("get_object")
    result = tool.fn(object_type="Document", object_name="ТестовыйДокумент", detail="posting")
    assert "ОбработкаПроведения" in result


def test_list_by_relation_registers_by_document(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("list_by_relation")
    result = tool.fn(
        relation="registers_by_document",
        object_type="Document",
        object_name="ТестовыйДокумент",
    )
    assert "ТестовыйРегистр" in result


def test_get_module_summary_mode(indexed_mcp, fixture_profile_config):
    mcp_server, config = indexed_mcp
    from packages.kb.indexer.scanner import scan_profile
    from packages.kb.indexer.models import FileKind

    bsl_path = next(
        e.path for e in scan_profile(config) if e.kind == FileKind.BSL
    )
    tool = mcp_server._tool_manager.get_tool("get_module")
    result = tool.fn(module_path=str(bsl_path), mode="summary")
    assert "ОбработкаПроведения" in result or "Модуль" in result


def test_get_module_procedure_mode(indexed_mcp, fixture_profile_config):
    mcp_server, config = indexed_mcp
    from packages.kb.indexer.scanner import scan_profile
    from packages.kb.indexer.models import FileKind

    bsl_path = next(
        e.path for e in scan_profile(config) if e.kind == FileKind.BSL
    )
    tool = mcp_server._tool_manager.get_tool("get_module")
    result = tool.fn(module_path=str(bsl_path), mode="event", name="ОбработкаПроведения")
    assert "Движения.ТестовыйРегистр" in result


def test_find_references_tool(indexed_mcp):
    mcp_server, _config = indexed_mcp
    tool = mcp_server._tool_manager.get_tool("find_references")
    result = tool.fn(identifier="Проведение", limit=5)
    assert isinstance(result, str)
