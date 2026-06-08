from packages.kb.indexer.cursor_mcp_status import (
    CursorMcpStatus,
    cursor_mcp_server_dir,
    get_cursor_mcp_status,
    normalize_mcp_url,
)
from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig


def _config(server_name: str = "1c-kb-test") -> ProfileConfig:
    return ProfileConfig(
        profile_name="test",
        display_name="Test",
        format="edt",
        root="/tmp",
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(collection="test"),
        mcp=McpConfig(server_name=server_name, port=8010),
        docker=DockerConfig(),
        config_path="/tmp/config.yaml",
    )


def test_normalize_mcp_url_localhost():
    assert normalize_mcp_url("http://localhost:8010/mcp") == normalize_mcp_url(
        "http://127.0.0.1:8010/mcp"
    )


def test_cursor_mcp_server_dir():
    assert cursor_mcp_server_dir("1c-kb-testbase") == "user-1c-kb-testbase"


def test_status_connected_when_tools_present(monkeypatch):
    config = _config("1c-kb-testbase")

    monkeypatch.setattr(
        "packages.kb.indexer.cursor_mcp_status.get_server_entry",
        lambda name: ({"url": "http://127.0.0.1:8010/mcp"}, "http://127.0.0.1:8010/mcp"),
    )
    monkeypatch.setattr("packages.kb.indexer.cursor_mcp_status.count_cursor_tools", lambda name: 4)
    monkeypatch.setattr(
        "packages.kb.indexer.cursor_mcp_status.probe_mcp_http",
        lambda url, timeout=4.0: (True, "ok"),
    )

    state = get_cursor_mcp_status(config, 8010, docker_running=True)
    assert state.status == CursorMcpStatus.CONNECTED
    assert state.cursor_tools_count == 4


def test_status_not_connected_when_container_stopped(monkeypatch):
    config = _config("1c-kb-testbase")

    monkeypatch.setattr(
        "packages.kb.indexer.cursor_mcp_status.get_server_entry",
        lambda name: ({"url": "http://127.0.0.1:8010/mcp"}, "http://127.0.0.1:8010/mcp"),
    )
    monkeypatch.setattr("packages.kb.indexer.cursor_mcp_status.count_cursor_tools", lambda name: 8)
    monkeypatch.setattr(
        "packages.kb.indexer.cursor_mcp_status.probe_mcp_http",
        lambda url, timeout=4.0: (True, "ok"),
    )

    state = get_cursor_mcp_status(config, 8010, docker_running=False)
    assert state.status == CursorMcpStatus.CONFIGURED
    assert "не запущен" in state.message


def test_status_missing_without_config(monkeypatch):
    config = _config("unknown-server")
    monkeypatch.setattr("packages.kb.indexer.cursor_mcp_status.get_server_entry", lambda name: (None, ""))
    monkeypatch.setattr("packages.kb.indexer.cursor_mcp_status.count_cursor_tools", lambda name: 0)
    monkeypatch.setattr(
        "packages.kb.indexer.cursor_mcp_status.probe_mcp_http",
        lambda url, timeout=4.0: (False, "down"),
    )

    state = get_cursor_mcp_status(config, 8010, docker_running=False)
    assert state.status == CursorMcpStatus.MISSING
