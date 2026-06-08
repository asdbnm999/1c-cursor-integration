"""Маршруты §2 Стандартные MCP-серверы (ТЗ §10.10)."""

from __future__ import annotations

import json
import time

from flask import Blueprint, Response, jsonify, render_template, request

from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG
from web.mcp.deploy import find_orphaned_searxng
from web.mcp.deploy_jobs import get_deploy_job, job_to_dict, start_deploy_job
from web.mcp.service import (
    _syntax_hbk_ready,
    apply_mcp_for_enabled,
    generate_server_compose,
    get_errors_help,
    get_logs,
    get_server_cfg,
    get_standard_mcp_status,
    stop_server,
    update_settings_payload,
)
from web.plugins.native_dialogs import pick_directory, pick_file
from web.routes import section_status_label
from web.settings import load_settings

mcp_page_bp = Blueprint("mcp_page", __name__, url_prefix="/mcp")
mcp_api_bp = Blueprint("mcp_api", __name__, url_prefix="/mcp/api")


@mcp_page_bp.route("/")
def mcp_index():
    settings = load_settings()
    status = settings.get("sections", {}).get("mcp", "not_started")
    return render_template(
        "mcp/index.html",
        page_title="Стандартные MCP-серверы",
        page_subtitle="Стандартные MCP-серверы",
        section_id="mcp",
        section_status=status,
        section_status_label=section_status_label(status),
        doc_link="/docs/02-mcp-docker.md",
    )


@mcp_api_bp.route("/status")
def api_status():
    with_health = request.args.get("health", "1") != "0"
    return jsonify(get_standard_mcp_status(with_health=with_health))


@mcp_api_bp.route("/generate-compose", methods=["POST"])
def api_generate_compose():
    payload = request.get_json(silent=True) or {}
    server = payload.get("server")
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return jsonify({"error": "server: searxng | 1c-syntax-helper"}), 400
    regenerate = bool(payload.get("regenerate_secret", False))
    try:
        result = generate_server_compose(server, regenerate_secret=regenerate)
        return jsonify({"ok": True, **result})
    except OSError as exc:
        return jsonify({"ok": False, "message": str(exc)}), 500


@mcp_api_bp.route("/deploy", methods=["POST"])
def api_deploy():
    payload = request.get_json(silent=True) or {}
    server = payload.get("server")
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return jsonify({"error": "server: searxng | 1c-syntax-helper"}), 400
    cfg = get_server_cfg(server)
    if server == SYNTAX_SLUG and not _syntax_hbk_ready(cfg):
        hbk_raw = (cfg.get("hbk_path") or "").strip()
        if not hbk_raw:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "Укажите путь к shcntx_ru.hbk — файл справки обязателен перед Deploy",
                    }
                ),
                400,
            )
        return (
            jsonify(
                {
                    "ok": False,
                    "message": f"Файл shcntx_ru.hbk не найден: {hbk_raw}",
                }
            ),
            400,
        )
    dry_run_mcp = bool(payload.get("dry_run_mcp", False))
    job = start_deploy_job(server, dry_run_mcp=dry_run_mcp)
    return jsonify({"ok": True, "job_id": job.id, "job": job_to_dict(job)})


@mcp_api_bp.route("/deploy/jobs/<job_id>")
def api_deploy_job(job_id: str):
    job = get_deploy_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Задача не найдена"}), 404
    return jsonify({"ok": True, "job": job_to_dict(job)})


@mcp_api_bp.route("/deploy/jobs/<job_id>/stream")
def api_deploy_job_stream(job_id: str):
    def generate():
        last_payload = ""
        while True:
            job = get_deploy_job(job_id)
            if not job:
                yield f"data: {json.dumps({'ok': False, 'error': 'Задача не найдена'}, ensure_ascii=False)}\n\n"
                break
            terminal = job.status.value in {"completed", "failed"}
            payload = json.dumps({"ok": True, "job": job_to_dict(job)}, ensure_ascii=False)
            if payload != last_payload or terminal:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if terminal:
                break
            time.sleep(0.5)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@mcp_api_bp.route("/stop", methods=["POST"])
def api_stop():
    payload = request.get_json(silent=True) or {}
    server = payload.get("server")
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return jsonify({"error": "server: searxng | 1c-syntax-helper"}), 400
    return jsonify(stop_server(server))


@mcp_api_bp.route("/logs")
def api_logs():
    server = request.args.get("server", SEARXNG_SLUG)
    tail = int(request.args.get("tail", 100))
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return jsonify({"error": "invalid server"}), 400
    return jsonify(get_logs(server, tail=tail))


@mcp_api_bp.route("/errors")
def api_errors():
    server = request.args.get("server", SEARXNG_SLUG)
    tail = int(request.args.get("tail", 100))
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return jsonify({"error": "invalid server"}), 400
    return jsonify(get_errors_help(server, tail=tail))


@mcp_api_bp.route("/settings", methods=["PUT"])
def api_settings():
    payload = request.get_json(silent=True) or {}
    if not payload.get("server"):
        return jsonify({"error": "Укажите server"}), 400
    return jsonify(update_settings_payload(payload))


@mcp_api_bp.route("/apply-mcp", methods=["POST"])
def api_apply_mcp():
    payload = request.get_json(silent=True) or {}
    dry_run = bool(payload.get("dry_run", False))
    return jsonify(apply_mcp_for_enabled(dry_run=dry_run))


@mcp_api_bp.route("/preview-mcp", methods=["POST"])
def api_preview_mcp():
    return jsonify(apply_mcp_for_enabled(dry_run=True))


@mcp_api_bp.route("/pick-compose-dir", methods=["POST"])
def api_pick_compose_dir():
    payload = request.get_json(silent=True) or {}
    server = payload.get("server", SEARXNG_SLUG)
    path = pick_directory("Выберите каталог для docker-compose")
    if not path:
        return jsonify({"cancelled": True})
    return jsonify(update_settings_payload({"server": server, "compose_dir": path}))


@mcp_api_bp.route("/pick-hbk", methods=["POST"])
def api_pick_hbk():
    path = pick_file("Выберите shcntx_ru.hbk", filetypes=[("HBK", "*.hbk"), ("Все", "*.*")])
    if not path:
        return jsonify({"cancelled": True})
    return jsonify(update_settings_payload({"server": SYNTAX_SLUG, "hbk_path": path}))


@mcp_api_bp.route("/orphans")
def api_orphans():
    return jsonify({"orphans": find_orphaned_searxng()})


@mcp_api_bp.route("/regenerate-secret", methods=["POST"])
def api_regenerate_secret():
    payload = request.get_json(silent=True) or {}
    if payload.get("server", SEARXNG_SLUG) != SEARXNG_SLUG:
        return jsonify({"error": "Только для searxng"}), 400
    result = generate_server_compose(SEARXNG_SLUG, regenerate_secret=True)
    return jsonify({"ok": True, **result})
