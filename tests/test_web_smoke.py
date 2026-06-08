"""Smoke-тест Flask-приложения (шаг 0)."""

from web.app import _browser_url, create_app


def test_browser_url_loopback_for_wildcard_bind():
    assert _browser_url("0.0.0.0", 8080) == "http://127.0.0.1:8080/"
    assert _browser_url("127.0.0.1", 9090) == "http://127.0.0.1:9090/"


def test_health_endpoint():
    app = create_app()
    client = app.test_client()
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["service"] == "1c-cursor-web"


def test_system_api():
    app = create_app()
    client = app.test_client()
    res = client.get("/api/system")
    assert res.status_code == 200
    data = res.get_json()
    assert "python" in data
    assert "docker" in data


def test_mcp_status_api():
    app = create_app()
    client = app.test_client()
    res = client.get("/api/mcp/status")
    assert res.status_code == 200
    assert "servers" in res.get_json()


def test_dashboard():
    app = create_app()
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    assert b"1C:Cursor" in res.data or "1C:Cursor".encode() in res.data


def test_section_pages():
    app = create_app()
    client = app.test_client()
    for path in ("/mcp/", "/kb/"):
        res = client.get(path)
        assert res.status_code == 200


def test_rules_section():
    app = create_app()
    client = app.test_client()
    res = client.get("/rules/")
    assert res.status_code == 200
    assert b"section-project" in res.data


def test_plugins_section():
    app = create_app()
    client = app.test_client()
    res = client.get("/plugins/")
    assert res.status_code == 200
    assert b"btn-install" in res.data
