"""Тесты портов KB 83xx (ТЗ §7.1, §11.2, §15)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig
from packages.kb.indexer.docker_compose import compose_project_name, render_compose_yaml
from packages.kb.indexer.docker_names import container_name
from packages.kb.indexer.profiles import PROJECT_ROOT, allocate_http_port


def _sample_config(profile_name: str = "testbase", port: int = 8301) -> ProfileConfig:
    return ProfileConfig(
        profile_name=profile_name,
        display_name="Test",
        format="edt",
        root=Path("/tmp/project"),
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path=f"data/profiles/{profile_name}/chroma", collection=profile_name),
        mcp=McpConfig(server_name=f"1c-kb-{profile_name}", port=port),
        docker=DockerConfig(compose_dir=""),
        config_path=PROJECT_ROOT / "profiles" / profile_name / "config.yaml",
    )


def test_allocate_http_port_starts_at_8301():
    with patch("packages.kb.indexer.profiles.list_profiles", return_value=[]):
        with patch("web.system_check.is_port_free", return_value=True):
            with patch("packages.kb.indexer.kb_ports._reserved_kb_ports", return_value=set()):
                assert allocate_http_port("newprofile") == 8301


def test_allocate_http_port_increments_by_index():
    with patch(
        "packages.kb.indexer.profiles.list_profiles",
        return_value=["alpha", "beta", "gamma"],
    ):
        with patch("web.system_check.is_port_free", return_value=True):
            with patch("packages.kb.indexer.kb_ports._reserved_kb_ports", return_value=set()):
                assert allocate_http_port("beta") == 8302
                assert allocate_http_port("newone") == 8304


def test_kb_compose_uses_83xx_and_mcp_naming():
    config = _sample_config("myproject", 8305)
    text = render_compose_yaml(config)
    assert compose_project_name("myproject") == "1c-kb-myproject-mcp"
    assert container_name("myproject") == "1c-kb-myproject-mcp"
    assert "name: 1c-kb-myproject-mcp" in text
    assert "8305:8000" in text


def test_mcp_config_default_port_8301():
    config = _sample_config()
    assert config.mcp.port == 8301
