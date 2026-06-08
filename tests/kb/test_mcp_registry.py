import json

from packages.kb.indexer.config import ProfileConfig, McpConfig, StoreConfig, IndexingConfig, DocsConfig, ChunkingConfig, EmbeddingsConfig, DockerConfig
from packages.kb.indexer.mcp_registry import merge_server, parse_mcp_json


def _minimal_config() -> ProfileConfig:
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
        mcp=McpConfig(server_name="1c-kb-test", port=8011),
        docker=DockerConfig(),
        config_path="/tmp/config.yaml",
    )


def test_merge_mcp_json():
    original = {"mcpServers": {"other": {"url": "http://localhost:9999/mcp"}}}
    config = _minimal_config()
    merged = merge_server(original, config, 8011)
    assert "1c-kb-test" in merged["mcpServers"]
    assert merged["mcpServers"]["1c-kb-test"]["url"] == "http://127.0.0.1:8011/mcp"
    assert "other" in merged["mcpServers"]


def test_parse_empty():
    data = parse_mcp_json("{}")
    assert "mcpServers" in data
