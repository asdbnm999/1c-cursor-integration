import json
from pathlib import Path

import pytest

from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig
from packages.kb.indexer.cursor_mcp_config import (
    apply_profile_to_cursor_mcp,
    cursor_settings_summary,
    list_mcp_backups,
    prune_old_mcp_backups,
    remove_servers_from_cursor_mcp,
    resolve_cursor_config_dir,
    restore_mcp_from_backup,
    save_cursor_dir,
)


def _config(profile_name: str = "demo") -> ProfileConfig:
    return ProfileConfig(
        profile_name=profile_name,
        display_name="Demo",
        format="xml_export",
        root="/tmp",
        src="",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path=f"data/profiles/{profile_name}/chroma", collection=profile_name),
        mcp=McpConfig(server_name=f"1c-kb-{profile_name}", port=8011),
        docker=DockerConfig(),
        config_path=Path(f"/tmp/{profile_name}/config.yaml"),
    )


def test_apply_merges_without_wiping_other_servers(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    cursor_dir = tmp_path / "cursor-config"
    cursor_dir.mkdir()
    mcp_path = cursor_dir / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {"mcpServers": {"other-mcp": {"url": "http://127.0.0.1:9/mcp"}}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    project_root = tmp_path / "proj"
    backups_dir = project_root / "data" / "cursor-mcp-backups"
    fake_home = tmp_path / "no-cursor-home"
    fake_home.mkdir()
    monkeypatch.setattr(cfg_mod, "PROJECT_ROOT", project_root)
    monkeypatch.setattr(cfg_mod, "MCP_BACKUPS_DIR", backups_dir)
    monkeypatch.setattr(cfg_mod, "cursor_home_dir", lambda: fake_home / ".cursor")
    monkeypatch.setattr(cfg_mod, "get_saved_cursor_dir", lambda: str(cursor_dir))
    (project_root / "data" / "profiles" / "demo").mkdir(parents=True)

    result = apply_profile_to_cursor_mcp(_config(), 8011)
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert "other-mcp" in data["mcpServers"]
    assert "1c-kb-demo" in data["mcpServers"]
    assert data["mcpServers"]["1c-kb-demo"]["url"] == "http://127.0.0.1:8011/mcp"
    assert result["backup_path"]
    backup = Path(result["backup_path"])
    assert backup.parent == backups_dir.resolve()
    assert backup.name.startswith("mcp.json.bak-")
    assert not list(cursor_dir.glob("mcp.json.bak-*"))


def test_resolve_uses_home_cursor_when_present(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    home_cursor = tmp_path / "home" / ".cursor"
    home_cursor.mkdir(parents=True)
    monkeypatch.setattr(cfg_mod, "cursor_home_dir", lambda: home_cursor)
    monkeypatch.setattr(cfg_mod, "cursor_home_dir_exists", lambda: True)

    assert resolve_cursor_config_dir() == home_cursor.resolve()


def test_settings_requires_custom_dir_when_home_missing(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    fake_home = tmp_path / "no-cursor-home"
    fake_home.mkdir()
    monkeypatch.setattr(cfg_mod, "cursor_home_dir", lambda: fake_home / ".cursor")
    monkeypatch.setattr(cfg_mod, "get_saved_cursor_dir", lambda: "")

    summary = cursor_settings_summary()
    assert summary["cursor_home_found"] is False
    assert summary["cursor_dir_ready"] is False

    custom = tmp_path / "my-cursor"
    custom.mkdir()
    save_cursor_dir(str(custom))
    monkeypatch.setattr(cfg_mod, "get_saved_cursor_dir", lambda: str(custom))

    summary2 = cursor_settings_summary()
    assert summary2["cursor_dir_ready"] is True
    assert summary2["cursor_dir"] == str(custom.resolve())


def test_prune_old_mcp_backups(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    backups_dir = tmp_path / "data" / "cursor-mcp-backups"
    backups_dir.mkdir(parents=True)
    old = backups_dir / "mcp.json.bak-20200101-120000"
    recent = backups_dir / "mcp.json.bak-20990101-120000"
    old.write_text("{}", encoding="utf-8")
    recent.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "MCP_BACKUPS_DIR", backups_dir)

    removed = prune_old_mcp_backups(max_age_days=3)
    assert "mcp.json.bak-20200101-120000" in removed
    assert old.exists() is False
    assert recent.exists() is True
    assert len(list_mcp_backups()) == 1


def test_remove_servers_keeps_other_entries(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    cursor_dir = tmp_path / "cursor-config"
    cursor_dir.mkdir()
    mcp_path = cursor_dir / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "other-mcp": {"url": "http://127.0.0.1:9/mcp"},
                    "1c-kb-demo": {"url": "http://127.0.0.1:8011/mcp"},
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    backups_dir = tmp_path / "proj" / "data" / "cursor-mcp-backups"
    fake_home = tmp_path / "no-cursor-home"
    fake_home.mkdir()
    monkeypatch.setattr(cfg_mod, "MCP_BACKUPS_DIR", backups_dir)
    monkeypatch.setattr(cfg_mod, "cursor_home_dir", lambda: fake_home / ".cursor")
    monkeypatch.setattr(cfg_mod, "get_saved_cursor_dir", lambda: str(cursor_dir))

    result = remove_servers_from_cursor_mcp(["1c-kb-demo"])
    data = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert result["removed"] == ["1c-kb-demo"]
    assert "other-mcp" in data["mcpServers"]
    assert "1c-kb-demo" not in data["mcpServers"]
    assert result["backup_path"]
    assert Path(result["backup_path"]).exists()


def test_restore_mcp_from_latest_backup(monkeypatch, tmp_path: Path):
    import packages.kb.indexer.cursor_mcp_config as cfg_mod

    cursor_dir = tmp_path / "cursor-config"
    cursor_dir.mkdir()
    mcp_path = cursor_dir / "mcp.json"
    backups_dir = tmp_path / "proj" / "data" / "cursor-mcp-backups"
    backups_dir.mkdir(parents=True)
    backup = backups_dir / "mcp.json.bak-20990101-120000"
    backup.write_text(
        json.dumps({"mcpServers": {"only-old": {"url": "http://127.0.0.1:1/mcp"}}}),
        encoding="utf-8",
    )
    mcp_path.write_text(
        json.dumps({"mcpServers": {"new": {"url": "http://127.0.0.1:2/mcp"}}}),
        encoding="utf-8",
    )

    fake_home = tmp_path / "no-cursor-home"
    fake_home.mkdir()
    monkeypatch.setattr(cfg_mod, "PROJECT_ROOT", tmp_path / "proj")
    monkeypatch.setattr(cfg_mod, "MCP_BACKUPS_DIR", backups_dir)
    monkeypatch.setattr(cfg_mod, "cursor_home_dir", lambda: fake_home / ".cursor")
    monkeypatch.setattr(cfg_mod, "get_saved_cursor_dir", lambda: str(cursor_dir))

    result = restore_mcp_from_backup()
    restored = json.loads(mcp_path.read_text(encoding="utf-8"))
    assert restored["mcpServers"]["only-old"]["url"] == "http://127.0.0.1:1/mcp"
    assert result["restored_from"] == str(backup.resolve())
    assert len(list_mcp_backups()) == 1
