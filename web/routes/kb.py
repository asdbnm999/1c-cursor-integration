"""Маршруты §3 Векторная база знаний (ТЗ §11.9)."""

from __future__ import annotations

import json
import tempfile
import time
from io import BytesIO
from pathlib import Path

from flask import Blueprint, Response, jsonify, render_template, request, send_file

from packages.kb.indexer.api_auth import api_token_configured
from packages.kb.indexer.api_errors import error_response, register_error_handlers
from packages.kb.indexer.checkpoint import checkpoint_summary, clear_checkpoint
from packages.kb.indexer.config import EmbeddingsConfig, load_config
from packages.kb.indexer.cursor_mcp_config import (
    apply_profile_to_cursor_mcp,
    cursor_settings_summary,
    restore_mcp_from_backup,
    save_cursor_dir,
)
from packages.kb.indexer.cursor_mcp_status import get_cursor_mcp_status
from web.cursor_mcp import sync_managed_mcp_entries
from packages.kb.indexer.docker_build import get_build_state, image_exists, start_build
from packages.kb.indexer.docker_compose import default_compose_dir
from packages.kb.indexer.docker_manager import (
    docker_available,
    get_container_logs,
    get_status as docker_status,
    mcp_entry_for_profile,
    start_container,
    remove_container,
    stop_container,
)
from packages.kb.indexer.embeddings import check_embeddings
from packages.kb.indexer.exceptions import IndexerError
from packages.kb.indexer.health import health_for_profile, health_system
from packages.kb.indexer.incremental import preview_incremental
from packages.kb.indexer.index_archive import export_index, import_index, repair_imported_profile_identity
from packages.kb.indexer.index_state import load_manifest
from packages.kb.indexer.jobs import (
    cancel_job,
    get_job,
    get_profile_job,
    job_to_dict,
    list_jobs,
    load_persisted_job,
    start_index_job,
)
from packages.kb.indexer.mcp_registry import (
    build_standalone_entry,
    format_mcp_json,
    merge_server,
    parse_mcp_json,
)
from packages.kb.indexer.profile_compare import compare_profiles
from packages.kb.indexer.profile_ops import (
    clone_profile,
    create_profile,
    delete_profile_completely,
    save_compose_dir,
    save_embeddings_settings,
    save_indexing_settings,
)
from packages.kb.indexer.profiles import list_profiles
from packages.kb.indexer.scanner import scan_profile
from packages.kb.indexer.store import count_chunks
from packages.kb.indexer.watcher import get_watch_status, start_watch, stop_watch
from packages.kb.indexer.wizard import run_wizard
from packages.kb.indexer.workflow_guards import (
    container_created,
    require_container_for_mcp,
    require_indexed_profile,
)
from packages.kb.indexer.workflow_status import compute_workflow_status
from packages.kb.paths import PROFILES_DIR, PROJECT_ROOT
from web.plugins.native_dialogs import pick_directory
from web.routes import section_status_label
from web.settings import load_settings

kb_page_bp = Blueprint("kb_page", __name__, url_prefix="/kb")
kb_api_bp = Blueprint("kb_api", __name__, url_prefix="/kb/api")


def _profile_file_count(config, *, full_scan: bool) -> int:
    if full_scan:
        try:
            return len(scan_profile(config))
        except Exception:
            return 0
    try:
        manifest = load_manifest(config)
        cached = len(manifest.get("files") or {})
        if cached:
            return cached
    except Exception:
        pass
    return 0


def _profile_list_item(name: str) -> dict:
    """Лёгкая карточка для /kb/ — без полного scan_profile и HTTP-probe MCP."""
    config = load_config(name)
    job = get_profile_job(name)
    container = docker_status(name)
    chunks = 0
    try:
        chunks = count_chunks(config)
    except Exception:
        pass
    file_count = _profile_file_count(config, full_scan=False)
    cursor_mcp = get_cursor_mcp_status(
        config,
        container.host_port or config.mcp.port,
        docker_running=container.running,
        probe=False,
    ).to_dict()
    return {
        "name": name,
        "display_name": config.display_name,
        "format": config.format,
        "chunks": chunks,
        "files": file_count,
        "docker": {"running": container.running},
        "index_job": _resolve_index_job(name, job, chunks),
        "workflow": compute_workflow_status(
            profile_name=name,
            chunks=chunks,
            index_job=_resolve_index_job(name, job, chunks),
            docker_running=container.running,
            cursor_mcp=cursor_mcp,
        ),
    }


def _profile_summary(name: str) -> dict:
    repair_imported_profile_identity(name)
    config = load_config(name)
    job = get_profile_job(name)
    container = docker_status(name)
    chunks = 0
    try:
        chunks = count_chunks(config)
    except Exception:
        pass
    if chunks > 0 and not (config.docker.compose_dir or "").strip():
        try:
            from packages.kb.indexer.profile_ops import ensure_default_compose_dir

            ensure_default_compose_dir(name)
            config = load_config(name)
        except Exception:
            pass
    file_count = _profile_file_count(config, full_scan=True)

    cursor_mcp = get_cursor_mcp_status(
        config,
        container.host_port or config.mcp.port,
        docker_running=container.running,
        probe=False,
    ).to_dict()

    return {
        "name": name,
        "display_name": config.display_name,
        "git_branch": config.git_branch,
        "format": config.format,
        "root": str(config.root),
        "src": config.src if config.format == "edt" else "",
        "collection": config.store.collection,
        "mcp_server_name": config.mcp.server_name,
        "mcp_port": container.host_port or config.mcp.port,
        "mcp_url": container.url,
        "chunks": chunks,
        "files": file_count,
        "docker": {
            "running": container.running,
            "container_id": container.container_id,
            "compose_dir": config.docker.compose_dir,
            "compose_dir_suggested": str(default_compose_dir(name)),
            "image_exists": image_exists(name),
            "build_status": get_build_state(name).status.value,
            "error": container.error,
        },
        "store_path": config.store.path,
        "index_job": _resolve_index_job(name, job, chunks),
        "cursor_mcp": cursor_mcp,
        "watch": get_watch_status(name),
        "embeddings": {
            "provider": config.embeddings.provider,
            "model": config.embeddings.model,
            "device": config.embeddings.device,
            "batch_size": config.embeddings.batch_size,
        },
        "indexing": {
            "include_forms": config.indexing.include_forms,
        },
        "checkpoint": checkpoint_summary(config),
        "workflow": compute_workflow_status(
            profile_name=name,
            chunks=chunks,
            index_job=_resolve_index_job(name, job, chunks),
            docker_running=container.running,
            cursor_mcp=cursor_mcp,
        ),
        "gates": {
            "docker_enabled": chunks > 0,
            "mcp_enabled": container_created(name),
        },
    }


def _job_dict(job) -> dict | None:
    if job is not None:
        return job_to_dict(job)
    return None


def _resolve_index_job(name: str, job, chunks: int) -> dict | None:
    """Не показывать завершённую задачу, если индекс пуст (профиль пересоздан)."""
    active = _job_dict(job)
    if active:
        return active
    persisted = load_persisted_job(name)
    if not persisted:
        return None
    if chunks <= 0 and persisted.get("status") in {"completed", "failed", "cancelled"}:
        return None
    if chunks <= 0 and persisted.get("status") in {"pending", "running"}:
        return None
    return persisted



@kb_api_bp.get("/system")
def api_system():
    ok, err = docker_available()
    return jsonify({
        "docker_available": ok,
        "docker_error": err,
        "profiles_dir": str(PROFILES_DIR),
        "api_token_required": api_token_configured(),
    })


@kb_api_bp.get("/cursor/settings")
def api_cursor_settings():
    return jsonify({"ok": True, **cursor_settings_summary()})


@kb_api_bp.put("/cursor/dir")
def api_cursor_dir():
    data = request.get_json(force=True)
    cursor_dir = (data.get("cursor_dir") or "").strip()
    if not cursor_dir:
        return jsonify({"ok": False, "error": "Укажите каталог Cursor"}), 400
    try:
        saved = save_cursor_dir(cursor_dir)
        return jsonify({"ok": True, **cursor_settings_summary(), "cursor_dir": saved})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/cursor/mcp/restore")
def api_cursor_mcp_restore():
    data = request.get_json(silent=True) or {}
    backup_path = (data.get("backup_path") or "").strip() or None
    try:
        result = restore_mcp_from_backup(backup_path)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/<name>/mcp/apply")
def api_mcp_apply(name: str):
    try:
        require_container_for_mcp(name)
        config = load_config(name)
        container = docker_status(name)
        port = container.host_port or config.mcp.port
        result = apply_profile_to_cursor_mcp(config, port)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/pick-directory")
def api_pick_directory():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "Выберите каталог проекта или XML-выгрузки 1С")
    path = pick_directory(title)
    if not path:
        return jsonify({"ok": False, "cancelled": True})
    return jsonify({"ok": True, "path": path})


@kb_api_bp.get("/profiles")
def api_profiles():
    return jsonify([_profile_list_item(n) for n in list_profiles()])


@kb_api_bp.post("/profiles")
def api_create_profile():
    data = request.get_json(force=True)
    name = data.get("name", "").strip()
    root = data.get("root", "").strip()
    fmt = data.get("format", "edt")
    display = data.get("display_name", "").strip()
    src = data.get("src", "src").strip() or "src"
    docs_enabled = bool(data.get("docs_enabled", True))
    include_forms = bool(data.get("include_forms", False))

    if not name or not root:
        return jsonify({
            "ok": False,
            "error": "Укажите имя и путь к проекту",
            "error_code": "VALIDATION_ERROR",
        }), 400

    try:
        path = create_profile(
            name=name,
            display_name=display or name,
            fmt=fmt,
            root=root,
            src=src,
            docs_enabled=docs_enabled,
            include_forms=include_forms,
        )
        return jsonify({"ok": True, "profile": path.parent.name})
    except Exception as exc:
        return error_response(exc)


@kb_api_bp.delete("/profiles/<name>")
def api_delete_profile(name: str):
    try:
        removed = delete_profile_completely(name)
        return jsonify({"ok": True, "removed": removed})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.get("/profiles/<name>")
def api_profile(name: str):
    try:
        return jsonify(_profile_summary(name))
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@kb_api_bp.post("/profiles/<name>/scan")
def api_scan(name: str):
    try:
        config = load_config(name)
        entries = scan_profile(config)
        kinds: dict[str, int] = {}
        for e in entries:
            kinds[e.kind.value] = kinds.get(e.kind.value, 0) + 1
        return jsonify({"ok": True, "total": len(entries), "kinds": kinds})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.get("/profiles/<name>/index/changes")
def api_index_changes(name: str):
    try:
        config = load_config(name)
        preview = preview_incremental(config)
        return jsonify({"ok": True, **preview})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/<name>/index")
def api_index(name: str):
    data = request.get_json(silent=True) or {}
    resume = bool(data.get("resume", False))
    incremental = bool(data.get("incremental", False))
    full = bool(data.get("full", not incremental))
    if resume:
        full = True
        incremental = False
    if incremental:
        full = False
    try:
        job = start_index_job(name, full=full, incremental=incremental, resume=resume)
        return jsonify({"ok": True, "job": _job_dict(job)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.get("/profiles/<name>/checkpoint")
def api_checkpoint(name: str):
    config = load_config(name)
    return jsonify({"ok": True, "checkpoint": checkpoint_summary(config)})


@kb_api_bp.delete("/profiles/<name>/checkpoint")
def api_checkpoint_clear(name: str):
    config = load_config(name)
    clear_checkpoint(config)
    return jsonify({"ok": True})


@kb_api_bp.get("/jobs/<job_id>")
def api_job(job_id: str):
    job = get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "Задача не найдена", "error_code": "JOB_NOT_FOUND"}), 404
    return jsonify({"ok": True, "job": _job_dict(job)})


@kb_api_bp.get("/jobs/<job_id>/stream")
def api_job_stream(job_id: str):
    def generate():
        last_payload = ""
        while True:
            job = get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'ok': False, 'error': 'Задача не найдена'})}\n\n"
                break
            payload = json.dumps({"ok": True, "job": job_to_dict(job)}, ensure_ascii=False)
            if payload != last_payload:
                yield f"data: {payload}\n\n"
                last_payload = payload
            if job.status.value in {"completed", "failed", "cancelled"}:
                break
            time.sleep(0.5)

    return Response(generate(), mimetype="text/event-stream")


@kb_api_bp.post("/jobs/<job_id>/cancel")
def api_job_cancel(job_id: str):
    try:
        job = cancel_job(job_id)
        return jsonify({"ok": True, "job": job_to_dict(job)})
    except IndexerError as exc:
        return error_response(exc)


@kb_api_bp.get("/profiles/<name>/jobs")
def api_profile_jobs(name: str):
    return jsonify([_job_dict(j) for j in list_jobs(name)])


@kb_api_bp.get("/health")
def api_health_system():
    return jsonify({"ok": True, **health_system()})


@kb_api_bp.get("/profiles/<name>/health")
def api_health_profile(name: str):
    try:
        return jsonify({"ok": True, **health_for_profile(name)})
    except IndexerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 404


@kb_api_bp.post("/wizard/preview")
def api_wizard_preview():
    data = request.get_json(force=True)
    root = (data.get("root") or "").strip()
    include_forms = bool(data.get("include_forms", False))
    if not root:
        return jsonify({"ok": False, "error": "Укажите путь к проекту"}), 400
    try:
        result = run_wizard(root, include_forms=include_forms)
        return jsonify({"ok": True, **result})
    except IndexerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/wizard/embeddings/check")
def api_wizard_embeddings_check():
    data = request.get_json(silent=True) or {}
    cfg = EmbeddingsConfig(
        provider=data.get("provider", "local"),
        device=data.get("device", "auto"),
        model=data.get("model", "intfloat/multilingual-e5-small"),
    )
    try:
        result = check_embeddings(cfg, load_model=True)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return error_response(exc)


@kb_api_bp.post("/profiles/<name>/watch/start")
def api_watch_start(name: str):
    try:
        return jsonify({"ok": True, **start_watch(name)})
    except IndexerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/<name>/watch/stop")
def api_watch_stop(name: str):
    return jsonify({"ok": True, **stop_watch(name)})


@kb_api_bp.get("/profiles/<name>/watch")
def api_watch_status(name: str):
    return jsonify({"ok": True, **get_watch_status(name)})


@kb_api_bp.get("/profiles/<name>/export")
def api_export_index(name: str):
    try:
        path = export_index(name)
        download_name = path.name if path.name.endswith(".tar.gz") else f"{path.stem}.tar.gz"
        return send_file(
            path,
            mimetype="application/x-compressed-tar",
            as_attachment=True,
            download_name=download_name,
        )
    except IndexerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/import")
def api_import_index():
    overwrite = bool(request.form.get("overwrite", False))
    target = (request.form.get("target_profile") or "").strip() or None
    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Загрузите архив .tar.gz или .tar"}), 400
    upload = request.files["file"]
    import tempfile

    try:
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
            upload.save(tmp.name)
            profile_name = import_index(tmp.name, target_profile=target, overwrite=overwrite)
        return jsonify({"ok": True, "profile": profile_name})
    except IndexerError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    finally:
        try:
            Path(tmp.name).unlink(missing_ok=True)
        except Exception:
            pass


@kb_api_bp.post("/profiles/compare")
def api_compare_profiles():
    data = request.get_json(force=True)
    a = (data.get("profile_a") or "").strip()
    b = (data.get("profile_b") or "").strip()
    if not a or not b:
        return jsonify({"ok": False, "error": "Укажите profile_a и profile_b"}), 400
    try:
        result = compare_profiles(a, b)
        return jsonify({"ok": True, **result})
    except IndexerError as exc:
        return error_response(exc)


@kb_api_bp.post("/profiles/compare/export")
def api_compare_export():
    data = request.get_json(force=True)
    a = (data.get("profile_a") or "").strip()
    b = (data.get("profile_b") or "").strip()
    fmt = (data.get("format") or "json").strip().lower()
    if not a or not b:
        return jsonify({"ok": False, "error": "Укажите profile_a и profile_b"}), 400
    try:
        result = compare_profiles(a, b)
        if fmt == "csv":
            lines = ["key,diff_fields,a_synonym,b_synonym,a_attrs,b_attrs"]
            for row in result.get("changed", []):
                diffs = "|".join(row.get("diff_fields", []))
                ra, rb = row.get("a", {}), row.get("b", {})
                lines.append(
                    f"{row.get('key','')},{diffs},"
                    f"{ra.get('synonym','')},{rb.get('synonym','')},"
                    f"{ra.get('attributes_count',0)},{rb.get('attributes_count',0)}"
                )
            content = "\n".join(lines)
            return Response(
                content,
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename=compare-{a}-{b}.csv"},
            )
        payload = json.dumps(result, ensure_ascii=False, indent=2)
        return Response(
            payload,
            mimetype="application/json",
            headers={"Content-Disposition": f"attachment; filename=compare-{a}-{b}.json"},
        )
    except IndexerError as exc:
        return error_response(exc)


@kb_api_bp.post("/profiles/<name>/clone")
def api_clone_profile(name: str):
    data = request.get_json(force=True)
    target = (data.get("target_name") or "").strip()
    display = (data.get("display_name") or "").strip()
    root = (data.get("root") or "").strip() or None
    if not target:
        return jsonify({"ok": False, "error": "Укажите target_name"}), 400
    try:
        copy_index = bool(data.get("copy_index", False))
        path = clone_profile(
            name,
            target,
            display_name=display,
            root=root,
            copy_index=copy_index,
            git_branch=(data.get("git_branch") or "").strip(),
        )
        return jsonify({"ok": True, "profile": path.parent.name, "copy_index": copy_index})
    except Exception as exc:
        return error_response(exc)


@kb_api_bp.get("/profiles/<name>/embeddings/check")
def api_embeddings_check(name: str):
    try:
        config = load_config(name)
        result = check_embeddings(config.embeddings, load_model=True)
        return jsonify({"ok": True, **result})
    except Exception as exc:
        return error_response(exc)


@kb_api_bp.put("/profiles/<name>/embeddings")
def api_embeddings_settings(name: str):
    data = request.get_json(force=True)
    try:
        emb = save_embeddings_settings(
            name,
            provider=data.get("provider"),
            model=data.get("model"),
            device=data.get("device"),
            batch_size=data.get("batch_size"),
        )
        return jsonify({"ok": True, "embeddings": emb})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.put("/profiles/<name>/indexing")
def api_indexing_settings(name: str):
    data = request.get_json(force=True)
    try:
        idx = save_indexing_settings(name, include_forms=data.get("include_forms"))
        return jsonify({"ok": True, "indexing": idx})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.get("/profiles/<name>/docker/build")
def api_docker_build_status(name: str):
    return jsonify({"ok": True, **get_build_state(name).to_dict()})


@kb_api_bp.post("/profiles/<name>/docker/build")
def api_docker_build(name: str):
    data = request.get_json(silent=True) or {}
    force = bool(data.get("force", False))
    try:
        require_indexed_profile(name)
        state = start_build(name, force=force)
        return jsonify({"ok": True, **state.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.put("/profiles/<name>/docker/compose-dir")
def api_docker_compose_dir(name: str):
    data = request.get_json(force=True)
    if data.get("use_default"):
        compose_dir = str(default_compose_dir(name))
    else:
        compose_dir = (data.get("compose_dir") or "").strip()
    if not compose_dir:
        return jsonify({"ok": False, "error": "Укажите директорию compose-проекта"}), 400
    try:
        require_indexed_profile(name)
        target = save_compose_dir(name, compose_dir)
        return jsonify({"ok": True, "compose_dir": str(target)})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/<name>/docker/start")
def api_docker_start(name: str):
    data = request.get_json(silent=True) or {}
    compose_dir = (data.get("compose_dir") or "").strip()
    rebuild = bool(data.get("rebuild", False))
    try:
        require_indexed_profile(name)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not compose_dir:
        config = load_config(name)
        compose_dir = config.docker.compose_dir
    if not compose_dir:
        from packages.kb.indexer.profile_ops import ensure_default_compose_dir

        compose_dir = ensure_default_compose_dir(name) or ""
    if not compose_dir:
        return jsonify({
            "ok": False,
            "error": "Укажите директорию для Docker Compose-проекта",
            "suggested": str(default_compose_dir(name)),
        }), 400
    try:
        status = start_container(name, compose_dir=compose_dir, rebuild=rebuild)
        config = load_config(name)
        payload: dict = {
            "ok": True,
            "running": status.running,
            "url": status.url,
            "host_port": status.host_port,
            "container_id": status.container_id,
            "compose_dir": config.docker.compose_dir,
            "port_auto_assigned": status.port_auto_assigned,
        }
        if status.port_auto_assigned and status.previous_port is not None:
            payload["previous_port"] = status.previous_port
            payload["message"] = (
                f"Порт {status.previous_port} был занят — назначен {status.host_port}."
            )
        return jsonify(payload)
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@kb_api_bp.post("/profiles/<name>/docker/stop")
def api_docker_stop(name: str):
    try:
        require_indexed_profile(name)
        status = stop_container(name)
        return jsonify({"ok": True, "running": status.running})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@kb_api_bp.post("/profiles/<name>/docker/remove")
def api_docker_remove(name: str):
    try:
        require_indexed_profile(name)
        remove_container(name)
        status = docker_status(name)
        return jsonify({"ok": True, "running": status.running, "container_id": status.container_id})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500


@kb_api_bp.get("/profiles/<name>/docker/logs")
def api_docker_logs(name: str):
    status = docker_status(name)
    config = load_config(name)
    build = get_build_state(name).to_dict()
    include_logs = request.args.get("logs") in {"1", "true", "yes"}
    return jsonify({
        "ok": True,
        "build": build,
        "container_running": status.running,
        "container_logs": get_container_logs(name) if status.running and include_logs else "",
        "url": status.url,
        "container_id": status.container_id,
        "compose_dir": config.docker.compose_dir,
    })


@kb_api_bp.get("/profiles/<name>/docker")
def api_docker_status(name: str):
    sync_managed_mcp_entries()
    status = docker_status(name)
    config = load_config(name)
    return jsonify({
        "running": status.running,
        "url": status.url,
        "host_port": status.host_port,
        "container_id": status.container_id,
        "compose_dir": config.docker.compose_dir,
        "compose_dir_suggested": str(default_compose_dir(name)),
        "error": status.error,
    })


@kb_api_bp.get("/profiles/<name>/mcp/cursor-status")
def api_mcp_cursor_status(name: str):
    try:
        config = load_config(name)
        container = docker_status(name)
        probe = "full" if request.args.get("full") in {"1", "true", "yes"} else "light"
        state = get_cursor_mcp_status(
            config,
            container.host_port or config.mcp.port,
            docker_running=container.running,
            probe=probe,
        )
        return jsonify({"ok": True, **state.to_dict()})
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.post("/profiles/<name>/mcp/merge")
def api_mcp_merge(name: str):
    try:
        require_container_for_mcp(name)
        config = load_config(name)
        container = docker_status(name)
        port = container.host_port or config.mcp.port

        if "file" in request.files:
            content = request.files["file"].read()
        else:
            data = request.get_json(force=True)
            content = data.get("mcp_json", "").encode("utf-8")

        mcp_data = parse_mcp_json(content)
        merged = merge_server(mcp_data, config, port, overwrite=True)
        merged_text = format_mcp_json(merged)
        merged_path = PROJECT_ROOT / "data" / "profiles" / name / "mcp-merged.json"
        merged_path.parent.mkdir(parents=True, exist_ok=True)
        merged_path.write_text(merged_text, encoding="utf-8")
        return jsonify({
            "ok": True,
            "mcp_json": merged_text,
            "server_name": config.mcp.server_name,
            "url": mcp_entry_for_profile(config, port)["url"],
            "full_file": True,
        })
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400


@kb_api_bp.get("/profiles/<name>/mcp/download")
def api_mcp_download(name: str):
    try:
        require_container_for_mcp(name)
        merged_path = PROJECT_ROOT / "data" / "profiles" / name / "mcp-merged.json"
        if merged_path.is_file():
            payload = merged_path.read_text(encoding="utf-8")
            filename = "mcp.json"
        else:
            config = load_config(name)
            container = docker_status(name)
            port = container.host_port or config.mcp.port
            standalone = build_standalone_entry(config, port)
            payload = format_mcp_json(standalone)
            filename = f"mcp-{name}-fragment.json"
        return send_file(
            BytesIO(payload.encode("utf-8")),
            mimetype="application/json",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400




@kb_page_bp.route("/")
def kb_index():
    from web.kb.service import update_kb_section_status_in_settings

    status = update_kb_section_status_in_settings()
    return render_template(
        "kb/index.html",
        page_title="Векторная база знаний проекта",
        page_subtitle="Векторная база знаний проекта",
        section_id="kb",
        section_status=status,
        section_status_label=section_status_label(status),
        doc_link="/docs/03-knowledge-base.md",
    )


@kb_page_bp.route("/profile/<name>")
def kb_profile_page(name: str):
    if name not in list_profiles():
        return "Профиль не найден", 404
    from web.kb.service import update_kb_section_status_in_settings

    status = update_kb_section_status_in_settings()
    return render_template(
        "kb/profile.html",
        profile_name=name,
        page_title=name,
        page_subtitle="Векторная база знаний проекта",
        section_id="kb",
        section_status=status,
        section_status_label=section_status_label(status),
        doc_link="/docs/03-knowledge-base.md",
    )


def register_kb_blueprints(app) -> None:
    """Регистрация KB blueprints и обработчиков ошибок."""
    register_error_handlers(app)
    app.register_blueprint(kb_page_bp)
    app.register_blueprint(kb_api_bp)
