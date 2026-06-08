"""Диагностика: Chroma, Docker, Cursor, embeddings, watcher."""

from __future__ import annotations

import shutil
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.cursor_mcp_status import get_cursor_mcp_status
from packages.kb.indexer.docker_build import image_exists, is_building
from packages.kb.indexer.docker_manager import docker_available, get_status as docker_status
from packages.kb.indexer.docker_names import image_name
from packages.kb.indexer.embeddings import check_embeddings
from packages.kb.indexer.exceptions import ProfileNotFoundError
from packages.kb.indexer.index_state import load_manifest
from packages.kb.indexer.profiles import profile_config_path, list_profiles
from packages.kb.indexer.scanner import scan_profile
from packages.kb.indexer.store import count_chunks
from packages.kb.indexer.jobs import get_profile_job
from packages.kb.indexer.watcher import get_watch_status


def _profile_state(chunks: int, job_active: bool, issues: list[str]) -> str:
    if chunks <= 0 and not job_active:
        return "new"
    if job_active:
        return "indexing"
    if issues:
        return "degraded"
    return "ready"


def health_for_profile(profile_name: str) -> dict:
    if profile_name not in list_profiles():
        raise ProfileNotFoundError(f"Профиль не найден: {profile_name}")

    config = load_config(profile_name)
    issues: list[str] = []
    checks: dict[str, dict] = {}

    # Source
    src_ok = config.source_base.exists()
    checks["source"] = {
        "ok": src_ok,
        "path": str(config.source_base),
        "format": config.format,
    }
    if not src_ok:
        issues.append(f"Каталог проекта недоступен: {config.source_base}")

    # Scan
    try:
        scan = scan_profile(config) if src_ok else []
        checks["scan"] = {"ok": src_ok, "files": len(scan)}
    except Exception as exc:
        checks["scan"] = {"ok": False, "error": str(exc)}
        issues.append(f"Сканирование: {exc}")

    # Chroma
    chunks = 0
    try:
        chunks = count_chunks(config)
        manifest = load_manifest(config)
        checks["chroma"] = {
            "ok": chunks > 0,
            "chunks": chunks,
            "manifest_files": len(manifest.get("files", {})),
            "collection": config.store.collection,
        }
        if chunks == 0:
            issues.append("Индекс пуст — выполните полную индексацию")
    except Exception as exc:
        checks["chroma"] = {"ok": False, "error": str(exc)}
        issues.append(f"Chroma: {exc}")

    # Embeddings
    emb = check_embeddings(config.embeddings)
    checks["embeddings"] = emb
    if not emb.get("ok"):
        issues.append(emb.get("message", "Embeddings недоступны"))

    # Docker
    d_ok, d_err = docker_available()
    container = docker_status(profile_name)
    checks["docker"] = {
        "ok": d_ok and container.running,
        "daemon": d_ok,
        "daemon_error": d_err,
        "container_running": container.running,
        "url": container.url,
        "image_built": image_exists(profile_name),
        "image": image_name(profile_name),
    }
    if d_ok and not container.running:
        issues.append("Docker доступен, но контейнер не запущен")

    # Cursor MCP
    cursor = get_cursor_mcp_status(
        config,
        container.host_port or config.mcp.port,
        docker_running=container.running,
    ).to_dict()
    checks["cursor_mcp"] = cursor
    if container.running and cursor.get("status") != "connected":
        issues.append(cursor.get("message", "MCP не подключён в Cursor"))

    # Watcher
    watch = get_watch_status(profile_name)
    checks["watcher"] = watch

    # Disk space
    store_path = Path(config.store.path)
    if not store_path.is_absolute():
        store_path = config.project_root / store_path
    try:
        usage = shutil.disk_usage(store_path.parent if store_path.exists() else config.project_root)
        free_gb = usage.free / (1024 ** 3)
        checks["disk"] = {"ok": free_gb >= 1.0, "free_gb": round(free_gb, 2)}
        if free_gb < 1.0:
            issues.append(f"Мало места на диске: {free_gb:.1f} GB")
    except Exception as exc:
        checks["disk"] = {"ok": True, "error": str(exc)}

    # Manifest age
    manifest = load_manifest(config)
    if manifest.get("updated_at"):
        checks["manifest"] = {"ok": True, "updated_at": manifest.get("updated_at")}
    else:
        checks["manifest"] = {"ok": chunks > 0, "message": "manifest без даты"}

    job = get_profile_job(profile_name)
    job_active = bool(job and job.status.value in {"pending", "running"})
    state = _profile_state(chunks, job_active, issues)

    return {
        "profile": profile_name,
        "state": state,
        "healthy": len(issues) == 0,
        "issues": issues,
        "checks": checks,
        "store_path": str(store_path),
    }


def health_system() -> dict:
    d_ok, d_err = docker_available()
    profiles = list_profiles()
    active_build = next((name for name in profiles if is_building(name)), None)
    profile_health = []
    for name in profiles:
        try:
            h = health_for_profile(name)
            profile_health.append({
                "name": name,
                "healthy": h["healthy"],
                "issues_count": len(h["issues"]),
            })
        except Exception as exc:
            profile_health.append({"name": name, "healthy": False, "error": str(exc)})

    return {
        "docker_available": d_ok,
        "docker_error": d_err,
        "docker_build_active": active_build,
        "profiles_count": len(profiles),
        "profiles": profile_health,
    }
