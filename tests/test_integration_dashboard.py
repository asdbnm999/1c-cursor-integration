"""Интеграция dashboard и статусов разделов (шаг 7)."""

from __future__ import annotations

import json

from web.app import create_app
from web.sections import SECTION_ORDER, build_sections_snapshot, refresh_all_section_statuses


def test_sections_snapshot_structure():
    snap = build_sections_snapshot(refresh=True)
    assert set(snap["sections"].keys()) == set(SECTION_ORDER)
    assert len(snap["cards"]) == 4
    assert len(snap["wizard_steps"]) == 4
    assert snap["summary"]["total"] == 4
    for card in snap["cards"]:
        assert card["status"] in {"not_started", "in_progress", "ready"}
        assert card["doc_link"].startswith("/docs/")


def test_api_sections_status():
    app = create_app()
    client = app.test_client()
    res = client.get("/api/sections/status")
    assert res.status_code == 200
    data = res.get_json()
    assert "sections" in data
    assert "cards" in data
    assert "wizard_steps" in data


def test_api_sections_refresh():
    app = create_app()
    client = app.test_client()
    res = client.post("/api/sections/refresh")
    assert res.status_code == 200
    data = res.get_json()
    assert set(data["sections"].keys()) == set(SECTION_ORDER)


def test_dashboard_has_four_cards_and_wizard():
    app = create_app()
    client = app.test_client()
    res = client.get("/")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "card-plugins" in html
    assert "card-mcp" in html
    assert "card-kb" in html
    assert "card-rules" in html
    assert "wizard-steps" in html
    assert "Мастер первого запуска" in html
    assert "btn-export-settings" in html


def test_system_api_ram_estimate():
    app = create_app()
    client = app.test_client()
    res = client.get("/api/system")
    assert res.status_code == 200
    data = res.get_json()
    assert "ram_estimate" in data
    assert "total_mb" in data["ram_estimate"]


def test_settings_export_import_roundtrip(tmp_path, monkeypatch):
    from web.paths import SETTINGS_PATH, CURSOR_SETTINGS_PATH
    from web.settings import load_settings

    app = create_app()
    client = app.test_client()

    export_res = client.get("/api/settings/export")
    assert export_res.status_code == 200
    bundle = export_res.get_json()
    assert "settings" in bundle
    assert "cursor" in bundle

    settings_before = load_settings()
    settings_before.setdefault("ui", {})["palette"] = "ocean"
    from web.settings import save_settings

    save_settings(settings_before)

    import_res = client.post(
        "/api/settings/import",
        data=json.dumps(bundle),
        content_type="application/json",
    )
    assert import_res.status_code == 200
    assert import_res.get_json().get("ok") is True


def test_serve_docs():
    app = create_app()
    client = app.test_client()
    res = client.get("/docs/README.md")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "docs-content" in html
    assert "<table>" in html or "<h1>" in html or "<h2>" in html
    assert "text/plain" not in (res.content_type or "")


def test_serve_docs_plugins_table():
    app = create_app()
    client = app.test_client()
    res = client.get("/docs/01-plugins.md")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "VS-плагины" in html
    assert "<table>" in html
    assert "|---" not in html


def test_refresh_all_persists():
    statuses = refresh_all_section_statuses(persist=True)
    from web.settings import load_settings

    stored = load_settings().get("sections", {})
    for key in SECTION_ORDER:
        assert stored.get(key) == statuses[key]
