"""Автовыбор свободного порта KB 8301–8399."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from packages.kb.indexer.kb_ports import (
    KB_PORT_MAX,
    KB_PORT_MIN,
    ensure_profile_host_port,
    find_free_kb_port,
    save_mcp_port,
)


def test_find_free_kb_port_prefers_first_free():
    with patch("web.system_check.is_port_free", side_effect=lambda p: p == 8303):
        with patch("packages.kb.indexer.kb_ports._reserved_kb_ports", return_value=set()):
            assert find_free_kb_port(preferred=8301) == 8303


def test_find_free_kb_port_skips_reserved():
    with patch("web.system_check.is_port_free", return_value=True):
        with patch(
            "packages.kb.indexer.kb_ports._reserved_kb_ports",
            return_value={8301, 8302},
        ):
            assert find_free_kb_port(preferred=8301) == 8303


def test_find_free_kb_port_raises_when_exhausted():
    with patch("web.system_check.is_port_free", return_value=False):
        with patch("packages.kb.indexer.kb_ports._reserved_kb_ports", return_value=set()):
            with pytest.raises(RuntimeError, match=str(KB_PORT_MIN)):
                find_free_kb_port()


def test_ensure_profile_host_port_keeps_free_port(monkeypatch, tmp_path):
    import packages.kb.indexer.kb_ports as kb_ports_mod
    from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig

    cfg = ProfileConfig(
        profile_name="demo",
        display_name="Demo",
        format="edt",
        root=tmp_path,
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path="data/profiles/demo/chroma", collection="demo"),
        mcp=McpConfig(server_name="1c-kb-demo", port=8301),
        docker=DockerConfig(),
        config_path=tmp_path / "config.yaml",
    )

    monkeypatch.setattr("packages.kb.indexer.config.load_config", lambda _name: cfg)
    monkeypatch.setattr("web.system_check.is_port_free", lambda _p: True)
    monkeypatch.setattr(kb_ports_mod, "_reserved_kb_ports", lambda **_: set())

    port, changed = ensure_profile_host_port("demo")
    assert port == 8301
    assert changed is False


def test_ensure_profile_host_port_picks_next_when_busy(monkeypatch, tmp_path):
    import packages.kb.indexer.kb_ports as kb_ports_mod
    from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig

    cfg = ProfileConfig(
        profile_name="demo",
        display_name="Demo",
        format="edt",
        root=tmp_path,
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path="data/profiles/demo/chroma", collection="demo"),
        mcp=McpConfig(server_name="1c-kb-demo", port=8301),
        docker=DockerConfig(),
        config_path=tmp_path / "config.yaml",
    )

    saved: list[int] = []

    monkeypatch.setattr("packages.kb.indexer.config.load_config", lambda _name: cfg)
    monkeypatch.setattr(
        "web.system_check.is_port_free",
        lambda p: p != 8301,
    )
    monkeypatch.setattr(kb_ports_mod, "_reserved_kb_ports", lambda **_: set())
    monkeypatch.setattr(
        kb_ports_mod,
        "save_mcp_port",
        lambda _profile, port: saved.append(port),
    )

    port, changed = ensure_profile_host_port("demo")
    assert port == 8302
    assert changed is True
    assert saved == [8302]


def test_save_mcp_port_updates_yaml(tmp_path, monkeypatch):
    import packages.kb.indexer.kb_ports as kb_ports_mod

    profile_dir = tmp_path / "profiles" / "demo"
    profile_dir.mkdir(parents=True)
    config_path = profile_dir / "config.yaml"
    config_path.write_text("mcp:\n  port: 8301\n", encoding="utf-8")

    monkeypatch.setattr(kb_ports_mod, "profile_config_path", lambda _name: config_path)

    save_mcp_port("demo", 8305)
    text = config_path.read_text(encoding="utf-8")
    assert "8305" in text
