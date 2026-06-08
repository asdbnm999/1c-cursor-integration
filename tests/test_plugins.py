"""Тесты §1 VS-плагинов (ТЗ §9.5, §15)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from web.app import create_app
from web.plugins.installer import InstallResult, install_vsix, record_installed_entries
from web.plugins.paths import default_extensions_dirs, resolve_extensions_dir
from web.plugins.service import compute_section_status, get_plugins_status
from web.plugins.vsix import (
    compare_versions,
    read_vsix_meta,
    scan_installed_extensions,
)
from web.settings import load_cursor_settings, load_settings, save_cursor_settings, save_settings


def _make_vsix(path: Path, publisher: str, name: str, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    package = json.dumps(
        {
            "publisher": publisher,
            "name": name,
            "version": version,
            "engines": {"vscode": "^1.60.0"},
        }
    ).encode()
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("extension/package.json", package)
        zf.writestr("extension/readme.md", "test")
    return path


@pytest.fixture
def isolated_plugins_env(tmp_path, monkeypatch):
    from web.paths import EXTENSIONS_DIR as REAL_EXTENSIONS

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    assets = tmp_path / "assets" / "extensions"
    assets.mkdir(parents=True)

    for name in (
        "1c-configuration-tree-2.10.7.vsix",
        "1c-syntax.language-1c-bsl-1.33.2.vsix",
    ):
        src = REAL_EXTENSIONS / name
        if src.is_file():
            (assets / name).write_bytes(src.read_bytes())

    monkeypatch.setattr("web.paths.DATA_DIR", data_dir)
    monkeypatch.setattr("web.paths.SETTINGS_PATH", data_dir / "settings.json")
    monkeypatch.setattr("web.paths.CURSOR_SETTINGS_PATH", data_dir / "cursor-settings.json")
    monkeypatch.setattr("web.paths.EXTENSIONS_DIR", assets)
    monkeypatch.setattr("web.plugins.vsix.EXTENSIONS_DIR", assets)
    monkeypatch.setattr("web.plugins.service.EXTENSIONS_DIR", assets)

    save_settings(
        {
            "ui": {"palette": "midnight"},
            "plugins": {"installed": []},
            "sections": {"plugins": "not_started"},
        }
    )
    save_cursor_settings({"cursor_extensions_dir": "", "mcp_config_path": ""})
    return tmp_path, assets


def test_read_bundled_vsix_metadata():
    from web.paths import EXTENSIONS_DIR

    meta = read_vsix_meta(EXTENSIONS_DIR / "1c-configuration-tree-2.10.7.vsix")
    assert meta.extension_id == "whiterabbit.1c-configuration-tree"
    assert meta.version == "2.10.7"
    assert meta.bundled is True


def test_compare_versions():
    assert compare_versions("1.33.2", "1.33.2") == 0
    assert compare_versions("2.10.7", "2.10.6") == 1
    assert compare_versions("1.0.0", "2.0.0") == -1


def test_scan_installed_extensions(tmp_path):
    ext_dir = tmp_path / "extensions"
    (ext_dir / "whiterabbit.1c-configuration-tree-2.10.7").mkdir(parents=True)
    (ext_dir / "1c-syntax.language-1c-bsl-1.33.1").mkdir(parents=True)
    found = scan_installed_extensions(ext_dir)
    assert "whiterabbit.1c-configuration-tree" in found
    assert found["whiterabbit.1c-configuration-tree"].version == "2.10.7"


def test_compute_section_status():
    from web.plugins.vsix import VsixMeta

    bundled = [
        VsixMeta(Path("/a.vsix"), "a.vsix", "p1", "ext1", "1.0.0", True),
        VsixMeta(Path("/b.vsix"), "b.vsix", "p2", "ext2", "2.0.0", True),
    ]

    class Inst:
        def __init__(self, version):
            self.version = version

    assert compute_section_status({}, bundled) == "not_started"
    assert compute_section_status({"p1.ext1": Inst("1.0.0")}, bundled) == "in_progress"
    both = {"p1.ext1": Inst("1.0.0"), "p2.ext2": Inst("2.0.0")}
    assert compute_section_status(both, bundled) == "ready"
    older = {"p1.ext1": Inst("1.0.0"), "p2.ext2": Inst("1.9.0")}
    assert compute_section_status(older, bundled) == "in_progress"


def test_install_not_installed(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    ext_dir.mkdir()
    vsix = _make_vsix(assets / "custom.vsix", "acme", "tool", "1.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""}
    )

    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        result = install_vsix(vsix, force=False)

    assert result.status == "ok"
    assert (ext_dir / "acme.tool-1.0.0").is_dir()


def test_install_same_version_skip(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    (ext_dir / "acme.tool-1.0.0").mkdir(parents=True)
    vsix = _make_vsix(assets / "custom.vsix", "acme", "tool", "1.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""}
    )

    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        result = install_vsix(vsix, force=False)

    assert result.status == "skipped"
    assert "Уже установлено" in result.message


def test_install_conflict_needs_force(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    (ext_dir / "acme.tool-1.0.0").mkdir(parents=True)
    vsix = _make_vsix(assets / "custom.vsix", "acme", "tool", "2.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""}
    )

    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        result = install_vsix(vsix, force=False)

    assert result.status == "conflict"
    assert result.needs_force is True


def test_install_force_reinstall(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    old = ext_dir / "acme.tool-1.0.0"
    old.mkdir(parents=True)
    (old / "old.txt").write_text("old")
    vsix = _make_vsix(assets / "custom.vsix", "acme", "tool", "2.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""}
    )

    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        result = install_vsix(vsix, force=True)

    assert result.status == "ok"
    assert (ext_dir / "acme.tool-2.0.0").is_dir()
    assert not old.exists()


def test_install_no_extensions_dir(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    missing = tmp_path / "nope" / "extensions"
    vsix = _make_vsix(assets / "x.vsix", "acme", "x", "1.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(missing), "mcp_config_path": ""}
    )

    result = install_vsix(vsix)
    assert result.status == "failed"
    assert "не существует" in result.message


def test_install_via_cli_mock(isolated_plugins_env, tmp_path):
    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    ext_dir.mkdir()
    vsix = _make_vsix(assets / "cli.vsix", "acme", "cliext", "1.0.0")

    save_cursor_settings(
        {"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""}
    )

    with patch("web.plugins.installer.find_cursor_cli", return_value="/usr/bin/cursor"):
        with patch("web.plugins.installer._install_via_cli", return_value=(True, "CLI ok")):
            result = install_vsix(vsix)

    assert result.status == "ok"
    assert result.method == "cli"


def test_record_installed_entries():
    results = [
        InstallResult("a", "ok", "ok", extension_id="p.n", version="1.0", method="manual"),
        InstallResult("b", "failed", "err"),
    ]
    entries = record_installed_entries(results)
    assert len(entries) == 1
    assert entries[0]["extension_id"] == "p.n"


def test_plugins_api_status(isolated_plugins_env):
    app = create_app()
    client = app.test_client()
    res = client.get("/plugins/api/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "bundled" in data
    assert "cursor" in data
    assert len(data["bundled"]) == 2


def test_plugins_api_cursor_dir(isolated_plugins_env, tmp_path):
    app = create_app()
    client = app.test_client()
    ext_dir = tmp_path / "my_ext"
    ext_dir.mkdir()

    res = client.put(
        "/plugins/api/cursor-dir",
        json={"path": str(ext_dir)},
    )
    assert res.status_code == 200
    assert load_cursor_settings()["cursor_extensions_dir"] == str(ext_dir)


def test_plugins_page_renders():
    app = create_app()
    client = app.test_client()
    res = client.get("/plugins/")
    assert res.status_code == 200
    assert b"VS" in res.data or "VS".encode() in res.data
    assert b"section_stub" not in res.data


def test_default_extensions_dirs_macos_or_linux():
    dirs = default_extensions_dirs()
    assert len(dirs) >= 1
    assert any("extensions" in str(d) for d in dirs)


def test_resolve_extensions_dir_configured(isolated_plugins_env, tmp_path):
    ext = tmp_path / "configured"
    ext.mkdir()
    save_cursor_settings(
        {"cursor_extensions_dir": str(ext), "mcp_config_path": ""}
    )
    path, source = resolve_extensions_dir()
    assert path == ext
    assert source == "configured"


def test_plugins_api_batch_install_partial(isolated_plugins_env, tmp_path):
    from web.app import create_app

    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    ext_dir.mkdir()
    ok_vsix = _make_vsix(assets / "ok.vsix", "acme", "good", "1.0.0")
    bad_path = str(assets / "missing.vsix")

    save_cursor_settings({"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""})

    app = create_app()
    client = app.test_client()
    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        res = client.post(
            "/plugins/api/install",
            json={"paths": [str(ok_vsix), bad_path], "force": False},
        )
    assert res.status_code == 200
    data = res.get_json()
    assert len(data["results"]) == 2
    statuses = {r["status"] for r in data["results"]}
    assert "ok" in statuses
    assert "failed" in statuses


def test_plugins_api_install_conflict_via_api(isolated_plugins_env, tmp_path):
    from web.app import create_app

    _, assets = isolated_plugins_env
    ext_dir = tmp_path / "cursor_ext"
    (ext_dir / "acme.tool-1.0.0").mkdir(parents=True)
    vsix = _make_vsix(assets / "upd.vsix", "acme", "tool", "2.0.0")

    save_cursor_settings({"cursor_extensions_dir": str(ext_dir), "mcp_config_path": ""})

    app = create_app()
    client = app.test_client()
    with patch("web.plugins.installer.find_cursor_cli", return_value=None):
        res = client.post(
            "/plugins/api/install",
            json={"paths": [str(vsix)], "force": False},
        )
    data = res.get_json()
    assert data["results"][0]["status"] == "conflict"
    assert data["results"][0]["needs_force"] is True
