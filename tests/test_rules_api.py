"""API и workflow §4 Rules (шаг 6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.conftest import EDT_FIXTURE, XML_FIXTURE
from web.app import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app()
    app.config["TESTING"] = True
    return app.test_client()


def _base_fields(schema: dict) -> dict:
    not_set = schema["constants"]["not_set"]
    fields = {
        "solution_type": {"choice": "доработанная", "custom": ""},
        "vcs": {"choice": "Без СКВ", "custom": ""},
        "dev_prefix": {"choice": "фд_", "custom": ""},
        "ai_patch_wrap": {"choice": schema["constants"]["wrap_enabled"], "custom": ""},
        "ai_patch_marker": {"choice": "Cursor", "custom": ""},
        "advanced": schema["advanced_initial_defaults"],
        "mcp": {"searxng": False, "syntax_helper": False, "kb_profiles": {}, "acknowledged": True},
    }
    return fields


@pytest.mark.skipif(not XML_FIXTURE.is_dir(), reason="XML fixture missing")
def test_rules_page_and_schema(client):
    res = client.get("/rules/")
    assert res.status_code == 200
    assert b"section-project" in res.data
    assert b"rules.js" in res.data

    res = client.get("/rules/api/schema")
    assert res.status_code == 200
    schema = res.get_json()
    assert "general_fields" in schema
    assert "apply_changes_via" not in [f["key"] for f in schema["general_fields"]]
    assert schema["advanced_initial_defaults"]["xml_create_metadata"] == "нет"
    assert schema["advanced_initial_defaults"]["edt_create_metadata"] == "нет"
    assert schema["advanced_recommended_defaults"]["xml_create_metadata"] == "с разрешения"


@pytest.mark.skipif(not XML_FIXTURE.is_dir(), reason="XML fixture missing")
def test_analyze_xml_fixture(client):
    res = client.post(
        "/rules/api/analyze",
        json={"export_path": str(XML_FIXTURE), "fields": {}},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["project_type"] == "xml"
    assert data["project_type_label"] == "Конфигуратор"
    assert "Configuration.xml" in data["report"] or "Конфигуратор" in data["report"]


@pytest.mark.skipif(not EDT_FIXTURE.is_dir(), reason="EDT fixture missing")
def test_analyze_edt_fixture(client):
    res = client.post(
        "/rules/api/detect-project",
        json={"export_path": str(EDT_FIXTURE)},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["project_type"] == "edt"
    assert data["project_type_label"] == "EDT"


@pytest.mark.skipif(not XML_FIXTURE.is_dir(), reason="XML fixture missing")
def test_generate_xml_with_mcp_section(client, tmp_path):
    schema_res = client.get("/rules/api/schema")
    schema = schema_res.get_json()
    fields = _base_fields(schema)
    fields["advanced"] = dict(schema["advanced_recommended_defaults"])

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    main = out_dir / "rules.md"

    res = client.post(
        "/rules/api/generate",
        json={
            "export_path": str(XML_FIXTURE),
            "output_path": str(main),
            "fields": fields,
            "advanced_ack": True,
            "write_to_cursor_rules": False,
            "confirm_unsafe_wrap": False,
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert Path(data["output_path"]).is_file()
    assert Path(data["event_log_path"]).is_file()
    text = Path(data["output_path"]).read_text(encoding="utf-8")
    assert "## MCP-серверы Cursor" in text
    assert "1С-правила-разработки" in Path(data["output_path"]).name or main.name in data["output_path"]


@pytest.mark.skipif(not XML_FIXTURE.is_dir(), reason="XML fixture missing")
def test_generate_409_unsafe_wrap(client):
    schema_res = client.get("/rules/api/schema")
    schema = schema_res.get_json()
    fields = _base_fields(schema)
    fields["ai_patch_wrap"] = {"choice": schema["constants"]["wrap_disabled"], "custom": ""}
    fields["advanced"] = dict(schema["advanced_initial_defaults"])

    res = client.post(
        "/rules/api/generate",
        json={
            "export_path": str(XML_FIXTURE),
            "fields": fields,
            "advanced_ack": True,
            "write_to_cursor_rules": False,
        },
    )
    assert res.status_code == 409
    assert res.get_json().get("needs_confirm") is True


def test_advanced_modal_defaults():
    from packages.rules.advanced_rules import advanced_modal_initial_defaults, recommended_advanced_defaults

    initial = advanced_modal_initial_defaults()
    rec = recommended_advanced_defaults()
    assert initial["xml_create_metadata"] == "нет"
    assert initial["edt_create_metadata"] == "нет"
    assert rec["xml_create_metadata"] == "с разрешения"
    assert rec["edt_create_metadata"] == "с разрешения"


def test_mcp_rules_section_text():
    from packages.rules.mcp_rules import build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": True, "syntax_helper": True, "kb_profiles": ["1c-kb-a", "1c-kb-b"]})
    assert "searxng" in text
    assert "1c-syntax-helper" in text
    assert "начале каждого диалога" in text


def test_mcp_rules_kb_tools_listed():
    from packages.rules.mcp_rules import KB_MCP_TOOLS, build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": False, "syntax_helper": False, "kb_profiles": ["1c-kb-demo"]})
    for tool in KB_MCP_TOOLS:
        assert f"`{tool}`" in text
    assert "1c-kb-demo" in text


def test_mcp_rules_kb_detail_levels():
    from packages.rules.mcp_rules import build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": False, "syntax_helper": False, "kb_profiles": ["1c-kb-demo"]})
    assert 'detail="movements"' in text
    assert 'detail="posting"' in text
    assert "list_by_relation" in text
    assert "find_references" in text


def test_mcp_rules_kb_no_tools_when_disabled():
    from packages.rules.mcp_rules import build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": False, "syntax_helper": False, "kb_profiles": []})
    assert "search_project" not in text
    assert "get_object" not in text
    assert "не подключена" in text


def test_mcp_rules_kb_deprecated_not_mentioned():
    from packages.rules.mcp_rules import build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": False, "syntax_helper": False, "kb_profiles": ["1c-kb-demo"]})
    assert "устаревшие" in text
    idx = text.find("| Tool | Когда вызывать |")
    idx_end = text.find("**Параметры ключевых tools:**")
    table = text[idx:idx_end]
    for deprecated in ("get_register_movements", "get_module_summary", "list_object_modules"):
        assert deprecated not in table


@pytest.mark.skipif(not EDT_FIXTURE.is_dir(), reason="EDT fixture missing")
def test_analyze_edt_full_report(client):
    res = client.post(
        "/rules/api/analyze",
        json={"export_path": str(EDT_FIXTURE), "fields": {}},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["project_type"] == "edt"
    assert "EDT" in data["report"] or "edt" in data["report"].lower()


@pytest.mark.skipif(not EDT_FIXTURE.is_dir(), reason="EDT fixture missing")
def test_generate_edt_subset(client, tmp_path):
    schema_res = client.get("/rules/api/schema")
    schema = schema_res.get_json()
    fields = _base_fields(schema)
    fields["advanced"] = dict(schema["advanced_initial_defaults"])
    fields["advanced"]["edt_create_metadata"] = "нет"
    fields["mcp"] = {
        "searxng": True,
        "syntax_helper": True,
        "kb_profiles": {},
        "acknowledged": True,
    }

    out_dir = tmp_path / "edt-out"
    out_dir.mkdir()
    main = out_dir / "rules-edt.md"

    res = client.post(
        "/rules/api/generate",
        json={
            "export_path": str(EDT_FIXTURE),
            "output_path": str(main),
            "fields": fields,
            "advanced_ack": True,
            "write_to_cursor_rules": False,
            "confirm_unsafe_wrap": False,
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    text = Path(data["output_path"]).read_text(encoding="utf-8")
    assert "searxng" in text.lower() or "MCP" in text
    assert "не создавать новые объекты метаданных" in text or "метаданных" in text


def test_mcp_rules_off_server_omitted():
    from packages.rules.mcp_rules import build_mcp_rules_section

    text = build_mcp_rules_section({"searxng": False, "syntax_helper": False, "kb_profiles": []})
    assert "searxng" not in text or "недоступен" in text.lower() or "не использовать" in text.lower()


def test_rules_workflow_validate_fields(client):
    schema = client.get("/rules/api/schema").get_json()
    fields = _base_fields(schema)
    res = client.post("/rules/api/validate-fields", json={"fields": fields, "advanced_ack": False})
    assert res.status_code == 200
    data = res.get_json()
    assert "main_complete" in data
    assert isinstance(data["main_complete"], bool)
    assert "manual_error" in data

    # Неполные поля → main_complete False
    bad = dict(fields)
    bad["solution_type"] = {"choice": schema["constants"]["not_set"], "custom": ""}
    res2 = client.post("/rules/api/validate-fields", json={"fields": bad})
    assert res2.get_json()["main_complete"] is False
