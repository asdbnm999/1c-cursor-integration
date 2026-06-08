"""API dashboard: диагностика системы, MCP, интеграция разделов (шаг 1 + 7)."""

from __future__ import annotations

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from web.cursor_mcp import check_all_mcp_servers, get_mcp_status, preview_diff, read_mcp_config
from web.docs_render import render_markdown_file
from web.paths import PROJECT_ROOT
from web.sections import build_sections_snapshot, refresh_all_section_statuses
from web.settings import export_settings, import_settings, load_settings
from web.system_check import run_system_diagnostics

dashboard_api_bp = Blueprint("dashboard_api", __name__)

DOCS_DIR = PROJECT_ROOT / "docs"


@dashboard_api_bp.route("/api/system")
def api_system():
    return jsonify(run_system_diagnostics())


@dashboard_api_bp.route("/api/mcp/status")
def api_mcp_status():
    with_health = request.args.get("health", "").lower() in {"1", "true", "yes"}
    return jsonify(get_mcp_status(with_health=with_health))


@dashboard_api_bp.route("/api/mcp/check", methods=["POST"])
def api_mcp_check():
    return jsonify(check_all_mcp_servers())


@dashboard_api_bp.route("/api/mcp/preview", methods=["POST"])
def api_mcp_preview():
    """Preview diff для будущего apply (без записи)."""
    payload = request.get_json(silent=True) or {}
    updates = payload.get("servers") or {}
    if not isinstance(updates, dict):
        return jsonify({"error": "servers должен быть объектом"}), 400
    current = read_mcp_config()
    from web.cursor_mcp import merge_servers

    merged = merge_servers(
        current,
        {k: {"url": v} if isinstance(v, str) else v for k, v in updates.items()},
        replace_keys=set(updates.keys()),
    )
    return jsonify({"diff": preview_diff(current, merged), "merged": merged})


@dashboard_api_bp.route("/api/settings/export")
def api_settings_export():
    return jsonify(export_settings())


@dashboard_api_bp.route("/api/settings/import", methods=["POST"])
def api_settings_import():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "ожидается JSON-объект"}), 400
    import_settings(payload)
    refresh_all_section_statuses(persist=True)
    return jsonify({"ok": True, "sections": build_sections_snapshot(refresh=True)})


@dashboard_api_bp.route("/api/sections/status")
def api_sections_status():
    refresh = request.args.get("refresh", "0").lower() in {"1", "true", "yes"}
    return jsonify(build_sections_snapshot(refresh=refresh))


@dashboard_api_bp.route("/api/sections/refresh", methods=["POST"])
def api_sections_refresh():
    statuses = refresh_all_section_statuses(persist=True)
    return jsonify({"sections": statuses, "snapshot": build_sections_snapshot(refresh=False)})


@dashboard_api_bp.route("/docs/<path:filename>")
def serve_docs(filename: str):
    """Пользовательская документация §22 — HTML для .md, файлы как есть для остального."""
    if ".." in filename or filename.startswith("/"):
        return jsonify({"error": "invalid path"}), 400

    docs_root = DOCS_DIR.resolve()
    path = (docs_root / filename).resolve()
    try:
        path.relative_to(docs_root)
    except ValueError:
        return jsonify({"error": "not found"}), 404

    if not path.is_file():
        return jsonify({"error": "not found"}), 404

    if path.suffix.lower() == ".md":
        title, html_body = render_markdown_file(path)
        return render_template(
            "docs/page.html",
            doc_title=title,
            doc_html=html_body,
            doc_path=filename,
        )

    return send_from_directory(path.parent, path.name)
