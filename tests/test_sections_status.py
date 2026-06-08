"""Тесты интеграции статусов разделов §6.4 (шаг 7/8)."""

from __future__ import annotations

from unittest.mock import patch

from web.sections import SECTION_ORDER, refresh_all_section_statuses


def test_refresh_all_returns_four_sections():
    with (
        patch("web.sections.get_plugins_status", return_value={"section_status": "not_started"}),
        patch("web.sections.get_standard_mcp_status", return_value={"servers": []}),
        patch("web.sections.compute_mcp_section_status", return_value="not_started"),
        patch("web.sections.compute_kb_section_status", return_value="not_started"),
        patch("web.sections.compute_rules_section_status", return_value="not_started"),
    ):
        statuses = refresh_all_section_statuses(persist=False)
    assert set(statuses.keys()) == set(SECTION_ORDER)
    assert len(statuses) == 4


def test_refresh_all_mcp_ready_propagates():
    with (
        patch("web.sections.get_plugins_status", return_value={"section_status": "ready"}),
        patch("web.sections.get_standard_mcp_status", return_value={"servers": [{"enabled": True, "ready": True}]}),
        patch("web.sections.compute_mcp_section_status", return_value="ready"),
        patch("web.sections.compute_kb_section_status", return_value="in_progress"),
        patch("web.sections.compute_rules_section_status", return_value="not_started"),
    ):
        statuses = refresh_all_section_statuses(persist=False)
    assert statuses["plugins"] == "ready"
    assert statuses["mcp"] == "ready"
    assert statuses["kb"] == "in_progress"


def test_section_status_labels_in_api():
    from web.app import create_app

    app = create_app()
    client = app.test_client()
    res = client.get("/api/sections/status")
    data = res.get_json()
    for card in data["cards"]:
        assert card["status_label"] in {"Не начато", "В процессе", "Готово"}
