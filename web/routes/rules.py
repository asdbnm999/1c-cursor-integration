"""Маршруты §4 Генерация файла правил (ТЗ §12.10)."""

from __future__ import annotations

import subprocess

from flask import Blueprint, jsonify, render_template, request

from packages.rules import analyze_export
from packages.rules.advanced_rules import ADVANCED_SKIP_LABEL
from packages.rules.form_api import (
    analysis_hints,
    format_analysis_report,
    get_form_schema,
)
from packages.rules.native_dialogs import pick_directory, pick_save_file
from web.routes import section_status_label
from web.rules.git_hints import git_hints_for_path
from web.rules.service import (
    advanced_all_skipped,
    generate_rules,
    get_mcp_form_defaults,
    get_rules_status,
    validate_manual_fields,
)
from web.settings import load_settings

rules_page_bp = Blueprint("rules_page", __name__, url_prefix="/rules")
rules_api_bp = Blueprint("rules_api", __name__, url_prefix="/rules/api")


def _pick_response(path: str | None, *, dialog: str) -> tuple:
    if path:
        return jsonify({"ok": True, "path": path}), 200
    return jsonify({"ok": False, "cancelled": True, "dialog": dialog}), 200


@rules_page_bp.route("/")
def rules_index():
    settings = load_settings()
    status = settings.get("sections", {}).get("rules", "not_started")
    project_path = (request.args.get("project_path") or "").strip()
    last = settings.get("rules", {}).get("last_output") or {}
    return render_template(
        "rules/index.html",
        page_title="Генерация файла правил",
        page_subtitle="Генерация файла правил",
        section_id="rules",
        section_status=status,
        section_status_label=section_status_label(status),
        doc_link="/docs/04-rules-generator.md",
        initial_project_path=project_path,
        last_output=last,
    )


@rules_api_bp.route("/schema")
def api_schema():
    return jsonify(get_form_schema())


@rules_api_bp.route("/status")
def api_status():
    return jsonify(get_rules_status())


@rules_api_bp.route("/mcp-defaults")
def api_mcp_defaults():
    return jsonify(get_mcp_form_defaults())


@rules_api_bp.route("/git-hints")
def api_git_hints():
    path = (request.args.get("path") or "").strip()
    if not path:
        return jsonify({"error": "Укажите path"}), 400
    return jsonify(git_hints_for_path(path))


@rules_api_bp.route("/pick-directory", methods=["POST"])
def api_pick_directory():
    try:
        path = pick_directory()
    except subprocess.TimeoutExpired:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Диалог выбора папки не ответил вовремя. Повторите или введите путь вручную.",
                }
            ),
            504,
        )
    return _pick_response(path, dialog="directory")


@rules_api_bp.route("/pick-save-file", methods=["POST"])
def api_pick_save_file():
    data = request.get_json(silent=True) or {}
    default_name = (data.get("default_name") or "1С-правила-разработки.md").strip()
    try:
        path = pick_save_file(default_name=default_name)
    except subprocess.TimeoutExpired:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Диалог сохранения не ответил вовремя. Повторите или введите путь вручную.",
                }
            ),
            504,
        )
    return _pick_response(path, dialog="save")


@rules_api_bp.route("/detect-project", methods=["POST"])
def api_detect_project():
    data = request.get_json(silent=True) or {}
    export_path = (data.get("export_path") or "").strip()
    if not export_path:
        return jsonify({"ok": False, "error": "Укажите путь к проекту."}), 400
    analysis = analyze_export(export_path)
    return jsonify(
        {
            "ok": analysis.is_valid_export,
            "project_type": analysis.project_type,
            "project_type_label": analysis.project_type_label,
            "errors": analysis.errors,
        }
    )


@rules_api_bp.route("/analyze", methods=["POST"])
def api_analyze():
    data = request.get_json(silent=True) or {}
    export_path = (data.get("export_path") or "").strip()
    if not export_path:
        return jsonify({"ok": False, "error": "Укажите путь к проекту."}), 400

    analysis = analyze_export(export_path)
    fields = data.get("fields") or {}
    git = git_hints_for_path(export_path) if analysis.project_type == "edt" else {}

    return jsonify(
        {
            "ok": analysis.is_valid_export,
            "project_type": analysis.project_type,
            "project_type_label": analysis.project_type_label,
            "report": format_analysis_report(analysis, form_fields=fields),
            "hints": analysis_hints(analysis),
            "git": git,
            "errors": analysis.errors,
            "warnings": analysis.warnings,
        }
    )


@rules_api_bp.route("/generate", methods=["POST"])
def api_generate():
    data = request.get_json(silent=True) or {}
    export_path = (data.get("export_path") or "").strip()
    if not export_path:
        return jsonify({"ok": False, "error": "Укажите путь к проекту."}), 400

    fields = data.get("fields") or {}

    if not data.get("advanced_ack"):
        return jsonify(
            {
                "ok": False,
                "error": "Откройте «Дополнительные правила» и сохраните настройки.",
            }
        ), 400

    if not (fields.get("mcp") or {}).get("acknowledged"):
        return jsonify(
            {
                "ok": False,
                "error": "Подтвердите настройки MCP (кнопка «Принять настройки MCP»).",
            }
        ), 400

    advanced = (fields.get("advanced") or {})
    if advanced_all_skipped(advanced, ADVANCED_SKIP_LABEL) and not data.get("confirm_all_skip"):
        return jsonify(
            {
                "ok": False,
                "needs_skip_confirm": True,
                "error": "Все дополнительные правила пропущены — в файле останутся общие формулировки.",
            }
        ), 409

    result = generate_rules(
        export_path,
        output_path=(data.get("output_path") or "").strip() or None,
        fields=fields,
        confirm_unsafe_wrap=bool(data.get("confirm_unsafe_wrap")),
        write_to_cursor_rules=bool(data.get("write_to_cursor_rules", True)),
    )
    if result.get("needs_confirm"):
        return jsonify(result), 409
    if not result.get("ok"):
        status = 400
        if result.get("needs_skip_confirm"):
            status = 409
        return jsonify(result), status
    return jsonify(result)


@rules_api_bp.route("/validate-fields", methods=["POST"])
def api_validate_fields():
    """Проверка заполненности для workflow UI."""
    data = request.get_json(silent=True) or {}
    fields = data.get("fields") or {}
    from web.rules.service import validate_main_fields_complete

    return jsonify(
        {
            "main_complete": validate_main_fields_complete(fields),
            "manual_error": validate_manual_fields(fields),
        }
    )
