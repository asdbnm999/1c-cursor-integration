"""Тесты vendoring Rules (шаг 2B)."""

from __future__ import annotations

from pathlib import Path


def test_rules_public_api_import():
    from packages.rules import ExportAnalysis, analyze_export, generate_rules_bundle

    assert callable(analyze_export)
    assert callable(generate_rules_bundle)
    assert ExportAnalysis is not None


def test_rules_modules():
    from packages.rules import advanced_rules, export_analyzer, field_choices, form_api

    assert hasattr(export_analyzer, "analyze_export")
    assert hasattr(form_api, "get_form_schema")
    assert hasattr(field_choices, "SOLUTION_TYPES")
    assert hasattr(advanced_rules, "ADVANCED_RULE_SPECS")


def test_rules_no_tk_only_modules():
    rules_dir = Path(__file__).resolve().parent.parent / "packages" / "rules"
    assert not (rules_dir / "choice_field.py").exists()
    assert not (rules_dir / "ui_theme.py").exists()
