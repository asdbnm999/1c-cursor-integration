from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.scanner import scan_profile
from packages.kb.indexer.store import count_chunks


MANIFEST_VERSION = 1


def manifest_path(config: ProfileConfig) -> Path:
    rel = Path("data") / "profiles" / config.profile_name / "index-manifest.json"
    return (config.project_root / rel).resolve()


def file_signature(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"mtime_ns": stat.st_mtime_ns, "size": stat.st_size}


def load_manifest(config: ProfileConfig) -> dict[str, Any]:
    path = manifest_path(config)
    if not path.exists():
        return {"version": MANIFEST_VERSION, "files": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": MANIFEST_VERSION, "files": {}}
    if not isinstance(data.get("files"), dict):
        data["files"] = {}
    return data


def save_manifest(config: ProfileConfig, data: dict[str, Any]) -> Path:
    path = manifest_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION,
        "profile": config.profile_name,
        "format": config.format,
        "project_root": str(config.root),
        "files": data.get("files", {}),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def save_manifest_from_scan(config: ProfileConfig) -> Path:
    files: dict[str, dict[str, int]] = {}
    for entry in scan_profile(config):
        path = Path(entry.path).resolve()
        if path.is_file():
            files[str(path)] = file_signature(path)
    return save_manifest(config, {"files": files})


def ensure_manifest(config: ProfileConfig) -> dict[str, Any]:
    """Если индекс уже есть, а manifest нет — зафиксировать текущее состояние без переиндексации."""
    data = load_manifest(config)
    if data.get("files"):
        return data
    if count_chunks(config) > 0:
        save_manifest_from_scan(config)
        return load_manifest(config)
    return data


def update_manifest_after_index(
    config: ProfileConfig,
    *,
    processed_paths: list[str] | None = None,
    deleted_paths: list[str] | None = None,
) -> None:
    data = load_manifest(config)
    files: dict[str, dict[str, int]] = dict(data.get("files", {}))

    for path_str in deleted_paths or []:
        files.pop(str(Path(path_str).resolve()), None)

    for path_str in processed_paths or []:
        path = Path(path_str).resolve()
        if path.is_file():
            files[str(path)] = file_signature(path)

    save_manifest(config, {"files": files})
