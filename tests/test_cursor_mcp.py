"""Тесты cursor_mcp (шаг 1)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx

from web.cursor_mcp import (
    backup_mcp_config,
    check_server_health,
    merge_servers,
    preview_diff,
    read_mcp_config,
    resolve_mcp_config_path,
)


def test_preview_diff_no_changes():
    cfg = {"mcpServers": {"a": {"url": "http://127.0.0.1:1/mcp"}}}
    assert "Изменений нет" in preview_diff(cfg, cfg)


def test_merge_does_not_remove_foreign_servers():
    current = {
        "mcpServers": {
            "custom": {"url": "http://127.0.0.1:9999/mcp"},
            "searxng": {"url": "http://127.0.0.1:8200/mcp"},
        }
    }
    merged = merge_servers(current, {"searxng": {"url": "http://127.0.0.1:8201/mcp"}})
    assert merged["mcpServers"]["custom"]["url"] == "http://127.0.0.1:9999/mcp"
    assert merged["mcpServers"]["searxng"]["url"] == "http://127.0.0.1:8201/mcp"


def test_backup_mcp_config(tmp_path: Path):
    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")
    with patch("web.cursor_mcp.MCP_BACKUPS_DIR", tmp_path / "backups"):
        backup = backup_mcp_config(cfg, ttl_days=3)
    assert backup is not None
    assert backup.exists()


def test_check_server_health_ok():
    response = httpx.Response(200, text="healthy", request=httpx.Request("GET", "http://127.0.0.1/health"))

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url):
            return response

        def head(self, url):
            return response

    with patch("web.cursor_mcp.httpx.Client", FakeClient):
        result = check_server_health("http://127.0.0.1:8201/mcp")
    assert result["health"] == "ok"


def test_read_mcp_config_missing(tmp_path: Path, monkeypatch):
    monkeypatch.setattr("web.cursor_mcp.resolve_mcp_config_path", lambda: tmp_path / "missing.json")
    data = read_mcp_config()
    assert data == {"mcpServers": {}}


def test_resolve_mcp_config_path_override(monkeypatch, tmp_path: Path):
    custom = tmp_path / "custom-mcp.json"
    monkeypatch.setattr(
        "web.cursor_mcp.load_cursor_settings",
        lambda: {"mcp_config_path": str(custom)},
    )
    assert resolve_mcp_config_path() == custom


def test_merge_selective_replace_keys():
    current = {
        "mcpServers": {
            "custom": {"url": "http://127.0.0.1:9999/mcp"},
            "searxng": {"url": "http://127.0.0.1:8200/mcp"},
            "1c-syntax-helper": {"url": "http://127.0.0.1:8203/mcp"},
        }
    }
    merged = merge_servers(
        current,
        {"searxng": {"url": "http://127.0.0.1:8201/mcp"}},
        replace_keys={"searxng"},
    )
    assert merged["mcpServers"]["searxng"]["url"] == "http://127.0.0.1:8201/mcp"
    assert merged["mcpServers"]["1c-syntax-helper"]["url"] == "http://127.0.0.1:8203/mcp"
    assert merged["mcpServers"]["custom"]["url"] == "http://127.0.0.1:9999/mcp"


def test_apply_standard_mcp_dry_run(tmp_path: Path, monkeypatch):
    from web.cursor_mcp import apply_standard_mcp

    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {"other": {"url": "http://127.0.0.1:1/mcp"}}}', encoding="utf-8")
    merged, diff = apply_standard_mcp(
        {"searxng": "http://127.0.0.1:8201/mcp"},
        config_path=cfg,
        dry_run=True,
    )
    assert merged["mcpServers"]["searxng"]["url"] == "http://127.0.0.1:8201/mcp"
    assert merged["mcpServers"]["other"]["url"] == "http://127.0.0.1:1/mcp"
    assert "8201" in diff
    assert cfg.read_text(encoding="utf-8").count("searxng") == 0


def test_apply_standard_mcp_writes_and_backup(tmp_path: Path, monkeypatch):
    from web.cursor_mcp import apply_standard_mcp, read_mcp_config

    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")
    backups = tmp_path / "backups"
    monkeypatch.setattr("web.cursor_mcp.MCP_BACKUPS_DIR", backups)

    apply_standard_mcp(
        {"searxng": "http://127.0.0.1:8201/mcp"},
        config_path=cfg,
        dry_run=False,
    )
    data = read_mcp_config(cfg)
    assert data["mcpServers"]["searxng"]["url"] == "http://127.0.0.1:8201/mcp"
    assert list(backups.glob("mcp-*.json"))


def test_apply_kb_profile_key_format(tmp_path: Path):
    from web.cursor_mcp import apply_standard_mcp, read_mcp_config

    cfg = tmp_path / "mcp.json"
    cfg.write_text('{"mcpServers": {}}', encoding="utf-8")

    from web.cursor_mcp import apply_kb_profile

    apply_kb_profile("myproject", "http://127.0.0.1:8301/mcp", config_path=cfg)
    data = read_mcp_config(cfg)
    assert "1c-kb-myproject" in data["mcpServers"]
    assert data["mcpServers"]["1c-kb-myproject"]["url"] == "http://127.0.0.1:8301/mcp"


def test_preview_diff_shows_change():
    before = {"mcpServers": {"a": {"url": "http://127.0.0.1:1/mcp"}}}
    after = {"mcpServers": {"a": {"url": "http://127.0.0.1:2/mcp"}}}
    diff = preview_diff(before, after)
    assert "Изменений нет" not in diff
    assert "127.0.0.1:2" in diff


def test_check_mcp_initialize_ok():
    from web.cursor_mcp import check_mcp_initialize

    class FakeResp:
        status_code = 200
        text = 'event: message\ndata: {"result":{"serverInfo":{"name":"t"}},"jsonrpc":"2.0","id":1}\n\n'

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None, headers=None):
            return FakeResp()

    with patch("web.cursor_mcp.httpx.Client", lambda **kw: FakeClient()):
        result = check_mcp_initialize("http://127.0.0.1:54035/mcp")
    assert result["health"] == "ok"


def test_remove_mcp_servers(tmp_path: Path, monkeypatch):
    from web.cursor_mcp import read_mcp_config, remove_mcp_servers

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        '{"mcpServers": {"searxng": {"url": "http://127.0.0.1:8201/mcp"}, "custom": {"url": "http://127.0.0.1:1/mcp"}}}',
        encoding="utf-8",
    )
    backups = tmp_path / "backups"
    monkeypatch.setattr("web.cursor_mcp.MCP_BACKUPS_DIR", backups)

    result = remove_mcp_servers(["searxng"], config_path=cfg)
    data = read_mcp_config(cfg)
    assert result["removed"] == ["searxng"]
    assert "searxng" not in data["mcpServers"]
    assert "custom" in data["mcpServers"]
    assert list(backups.glob("mcp-*.json"))


def test_sync_managed_mcp_entries_removes_missing_standard(monkeypatch, tmp_path: Path):
    from web.cursor_mcp import read_mcp_config, sync_managed_mcp_entries

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        '{"mcpServers": {"searxng": {"url": "http://127.0.0.1:8201/mcp"}, "1c-kb-gone": {"url": "http://127.0.0.1:8301/mcp"}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr("web.cursor_mcp.resolve_mcp_config_path", lambda: cfg)
    monkeypatch.setattr(
        "web.mcp.deploy.container_status",
        lambda name: {"health": "missing"},
    )
    monkeypatch.setattr("web.settings.load_settings", lambda: {"mcp": {"standard": {}}})
    monkeypatch.setattr("packages.kb.indexer.profiles.list_profiles", lambda: [])

    removed = sync_managed_mcp_entries(config_path=cfg)
    data = read_mcp_config(cfg)
    assert "searxng" in removed
    assert "1c-kb-gone" in removed
    assert data["mcpServers"] == {}


def test_get_mcp_status_configured_without_health(tmp_path: Path):
    from web.cursor_mcp import get_mcp_status

    cfg = tmp_path / "mcp.json"
    cfg.write_text(
        '{"mcpServers": {"searxng": {"url": "http://127.0.0.1:8201/mcp"}}}',
        encoding="utf-8",
    )
    status = get_mcp_status(cfg, with_health=False)
    assert status["summary"] == "configured"
    assert "searxng" in status["servers"]
