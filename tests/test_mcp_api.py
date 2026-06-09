"""API-тесты §2 MCP (без docker compose up)."""

from __future__ import annotations

from web.app import create_app


def test_mcp_page_loads():
    app = create_app()
    client = app.test_client()
    res = client.get("/mcp/")
    assert res.status_code == 200
    assert "Стандартные MCP" in res.get_data(as_text=True)


def test_mcp_api_status():
    app = create_app()
    client = app.test_client()
    res = client.get("/mcp/api/status?health=0")
    assert res.status_code == 200
    data = res.get_json()
    assert "servers" in data
    assert len(data["servers"]) == 2
    assert data["section_status"] in ("not_started", "in_progress", "ready")


def test_mcp_generate_compose_searxng(tmp_path, monkeypatch):
    app = create_app()
    client = app.test_client()

    def fake_get_cfg(slug):
        from web.mcp.constants import default_server_settings

        cfg = default_server_settings(slug)
        cfg["compose_dir"] = str(tmp_path / "searxng")
        cfg["secret_key"] = "x"
        return cfg

    monkeypatch.setattr("web.mcp.service.get_server_cfg", fake_get_cfg)
    monkeypatch.setattr("web.mcp.service.save_server_cfg", lambda slug, u: {**fake_get_cfg(slug), **u})

    res = client.post("/mcp/api/generate-compose", json={"server": "searxng"})
    assert res.status_code == 200
    assert res.get_json().get("ok") is True
    assert (tmp_path / "searxng" / "docker-compose.yml").is_file()


def test_mcp_preview_mcp():
    app = create_app()
    client = app.test_client()
    res = client.post("/mcp/api/preview-mcp", json={})
    assert res.status_code == 200
    data = res.get_json()
    assert "diff" in data


def test_mcp_page_has_docker_root_editor():
    app = create_app()
    client = app.test_client()
    html = client.get("/mcp/").get_data(as_text=True)
    assert "docker-root-input" in html
    assert "btn-save-docker-root" in html


def test_mcp_docker_root_put(tmp_path, monkeypatch):
    from web.settings import load_settings, save_settings

    settings_path = tmp_path / "settings.json"
    monkeypatch.setattr("web.paths.SETTINGS_PATH", settings_path)
    monkeypatch.setattr("web.paths.SETTINGS_EXAMPLE_PATH", tmp_path / "missing.example")

    old_root = tmp_path / "old_docker"
    new_root = tmp_path / "new_docker"
    old_root.mkdir()
    save_settings(load_settings())
    data = load_settings()
    data["docker"]["root"] = str(old_root)
    save_settings(data)

    app = create_app()
    client = app.test_client()
    res = client.put("/mcp/api/docker-root", json={"root": str(new_root)})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["docker_root"] == str(new_root.resolve())

    updated = load_settings()
    assert updated["docker"]["root"] == str(new_root.resolve())
    assert updated["mcp"]["standard"]["searxng"]["compose_dir"] == str(new_root / "searxng")
    assert updated["mcp"]["standard"]["1c-syntax-helper"]["compose_dir"] == str(new_root / "1c-syntax")


def test_mcp_docker_root_rejects_empty():
    app = create_app()
    client = app.test_client()
    res = client.put("/mcp/api/docker-root", json={"root": "   "})
    assert res.status_code == 400
    assert res.get_json()["ok"] is False


def test_mcp_status_includes_default_docker_root():
    app = create_app()
    client = app.test_client()
    data = client.get("/mcp/api/status?health=0").get_json()
    assert "default_docker_root" in data
    assert data["default_docker_root"]
