"""Маршруты §1 VS-плагины: страница и API (ТЗ §9.8)."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, render_template, request

from web.plugins.installer import InstallResult, install_vsix
from web.plugins.native_dialogs import pick_directory, pick_vsix_file
from web.plugins.service import (
    add_vsix_from_picker,
    apply_install_results,
    get_plugins_status,
    save_cursor_extensions_dir,
)
from web.routes import section_status_label
from web.settings import load_settings

plugins_page_bp = Blueprint("plugins_page", __name__, url_prefix="/plugins")
plugins_api_bp = Blueprint("plugins_api", __name__, url_prefix="/plugins/api")


@plugins_page_bp.route("/")
def plugins_index():
    settings = load_settings()
    status = settings.get("sections", {}).get("plugins", "not_started")
    return render_template(
        "plugins/index.html",
        page_title="VS-плагины для 1С",
        page_subtitle="VS-плагины для 1С",
        section_id="plugins",
        section_status=status,
        section_status_label=section_status_label(status),
        doc_link="/docs/01-plugins.md",
    )


@plugins_api_bp.route("/status")
def api_status():
    return jsonify(get_plugins_status())


@plugins_api_bp.route("/install", methods=["POST"])
def api_install():
    payload = request.get_json(silent=True) or {}
    paths = payload.get("paths") or []
    if not isinstance(paths, list) or not paths:
        return jsonify({"error": "Укажите paths — список путей к VSIX"}), 400
    force = bool(payload.get("force", False))
    skip_paths = {str(p) for p in (payload.get("skip_paths") or [])}

    results: list[InstallResult] = []
    for raw in paths:
        path_str = str(raw)
        if path_str in skip_paths:
            results.append(
                InstallResult(
                    path=path_str,
                    status="skipped",
                    message="Пропущено пользователем",
                )
            )
            continue
        results.append(install_vsix(Path(path_str), force=force))

    apply_install_results(results)
    status = get_plugins_status()

    return jsonify(
        {
            "results": [
                {
                    "path": r.path,
                    "status": r.status,
                    "message": r.message,
                    "extension_id": r.extension_id,
                    "version": r.version,
                    "method": r.method,
                    "needs_force": r.needs_force,
                }
                for r in results
            ],
            "section_status": status["section_status"],
            "conflicts": [r.path for r in results if r.status == "conflict"],
        }
    )


@plugins_api_bp.route("/pick-vsix", methods=["POST"])
def api_pick_vsix():
    picked = pick_vsix_file("Выберите файл VSIX для добавления")
    if not picked:
        return jsonify({"ok": False, "cancelled": True})
    result = add_vsix_from_picker(picked)
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)


@plugins_api_bp.route("/pick-cursor-dir", methods=["POST"])
def api_pick_cursor_dir():
    picked = pick_directory("Выберите каталог расширений Cursor")
    if not picked:
        return jsonify({"ok": False, "cancelled": True})
    return jsonify(save_cursor_extensions_dir(picked))


@plugins_api_bp.route("/cursor-dir", methods=["PUT"])
def api_cursor_dir():
    payload = request.get_json(silent=True) or {}
    path = payload.get("path")
    if path is None:
        return jsonify({"error": "Укажите path"}), 400
    result = save_cursor_extensions_dir(str(path))
    if not result.get("ok"):
        return jsonify(result), 400
    return jsonify(result)
