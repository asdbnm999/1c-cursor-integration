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
