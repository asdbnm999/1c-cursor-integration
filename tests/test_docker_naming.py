"""Тесты 1C:Cursor."""

from web.docker_naming import auxiliary_name, mcp_json_key, mcp_stack_name


def test_mcp_stack_name():
    assert mcp_stack_name("searxng") == "searxng-mcp"
    assert mcp_stack_name("1c-syntax-helper") == "1c-syntax-helper-mcp"
    assert mcp_stack_name("1c-kb-myproject") == "1c-kb-myproject-mcp"


def test_auxiliary_name():
    assert auxiliary_name("searxng", "valkey") == "searxng-mcp-valkey"
    assert auxiliary_name("searxng", "core") == "searxng-mcp-core"
    assert auxiliary_name("1c-syntax-helper", "es") == "1c-syntax-helper-mcp-es"


def test_mcp_json_key():
    assert mcp_json_key("searxng-mcp") == "searxng"
    assert mcp_json_key("1c-kb-test") == "1c-kb-test"


def test_merge_servers_preserves_foreign():
    from web.cursor_mcp import merge_servers

    current = {"mcpServers": {"custom": {"url": "http://127.0.0.1:9999/mcp"}, "searxng": {"url": "old"}}}
    merged = merge_servers(current, {"searxng": {"url": "http://127.0.0.1:8201/mcp"}})
    assert merged["mcpServers"]["custom"]["url"] == "http://127.0.0.1:9999/mcp"
    assert merged["mcpServers"]["searxng"]["url"] == "http://127.0.0.1:8201/mcp"
