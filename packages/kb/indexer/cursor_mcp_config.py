from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.mcp_registry import format_mcp_json, merge_server, parse_mcp_json
from packages.kb.indexer.profiles import PROJECT_ROOT

SETTINGS_PATH = PROJECT_ROOT / "data" / "cursor-settings.json"
MCP_BACKUPS_DIR = PROJECT_ROOT / "data" / "cursor-mcp-backups"
BACKUP_NAME_PREFIX = "mcp.json.bak-"
BACKUP_MAX_AGE_DAYS = 3


def cursor_home_dir() -> Path:
    return Path.home() / ".cursor"


def cursor_home_dir_exists() -> bool:
    return cursor_home_dir().is_dir()


def _load_settings() -> dict[str, Any]:
    if not SETTINGS_PATH.is_file():
        return {}
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_settings(data: dict[str, Any]) -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def get_saved_cursor_dir() -> str:
    return str(_load_settings().get("cursor_dir") or "").strip()


def save_cursor_dir(cursor_dir: str) -> str:
    target = Path(cursor_dir).expanduser().resolve()
    if not target.is_dir():
        raise ValueError(f"Каталог не найден: {target}")
    data = _load_settings()
    data["cursor_dir"] = str(target)
    _save_settings(data)
    return str(target)


def resolve_cursor_config_dir() -> Path:
    home = cursor_home_dir()
    if home.is_dir():
        return home.resolve()
    saved = get_saved_cursor_dir()
    if saved:
        custom = Path(saved).expanduser().resolve()
        if custom.is_dir():
            return custom
        raise ValueError(f"Сохранённый каталог Cursor не найден: {custom}")
    raise ValueError(
        "Каталог ~/.cursor не найден. Укажите директорию конфигурации Cursor вручную.",
    )


def cursor_mcp_json_path_resolved() -> Path:
    return resolve_cursor_config_dir() / "mcp.json"


def _ensure_backups_dir() -> Path:
    MCP_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    return MCP_BACKUPS_DIR


def _backup_file_name(stamp: str) -> str:
    return f"{BACKUP_NAME_PREFIX}{stamp}"


def _backup_path_for_stamp(stamp: str) -> Path:
    return _ensure_backups_dir() / _backup_file_name(stamp)


def _backup_timestamp(path: Path) -> datetime | None:
    stamp = path.name[len(BACKUP_NAME_PREFIX) :]
    if len(stamp) != 15:
        return None
    try:
        return datetime.strptime(stamp, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def prune_old_mcp_backups(max_age_days: int = BACKUP_MAX_AGE_DAYS) -> list[str]:
    backup_dir = _ensure_backups_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    removed: list[str] = []
    for path in backup_dir.glob(f"{BACKUP_NAME_PREFIX}*"):
        if not path.is_file():
            continue
        stamp = _backup_timestamp(path)
        if stamp is None:
            stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        if stamp < cutoff:
            path.unlink(missing_ok=True)
            removed.append(path.name)
    return removed


def _is_valid_backup_path(path: Path) -> bool:
    try:
        resolved = path.resolve()
        root = _ensure_backups_dir().resolve()
    except OSError:
        return False
    if root not in resolved.parents:
        return False
    return resolved.name.startswith(BACKUP_NAME_PREFIX)


def list_mcp_backups() -> list[dict[str, str]]:
    prune_old_mcp_backups()
    backup_dir = _ensure_backups_dir()
    items = sorted(
        backup_dir.glob(f"{BACKUP_NAME_PREFIX}*"),
        key=lambda path: path.name,
        reverse=True,
    )
    return [{"path": str(path), "name": path.name} for path in items]


def restore_mcp_from_backup(backup_path: str | None = None) -> dict[str, str]:
    cfg_dir = resolve_cursor_config_dir()
    mcp_path = cfg_dir / "mcp.json"

    if backup_path:
        src = Path(backup_path).expanduser().resolve()
    else:
        backups = list_mcp_backups()
        if not backups:
            raise ValueError("Бэкап mcp.json не найден")
        src = Path(backups[0]["path"]).resolve()

    if not _is_valid_backup_path(src):
        raise ValueError("Недопустимый путь к бэкапу")
    if not src.is_file():
        raise FileNotFoundError(f"Бэкап не найден: {src}")

    shutil.copy2(src, mcp_path)
    return {
        "mcp_json_path": str(mcp_path),
        "restored_from": str(src),
        "backup_name": src.name,
    }


def cursor_settings_summary() -> dict[str, Any]:
    home_found = cursor_home_dir_exists()
    saved = get_saved_cursor_dir()
    backups = list_mcp_backups()
    latest_backup = backups[0]["path"] if backups else ""
    try:
        cfg_dir = resolve_cursor_config_dir()
        mcp_path = cfg_dir / "mcp.json"
        resolved = str(cfg_dir)
        ready = True
    except ValueError as exc:
        cfg_dir = None
        mcp_path = None
        resolved = ""
        ready = False
        error = str(exc)
    else:
        error = ""

    return {
        "cursor_home_found": home_found,
        "cursor_dir": resolved,
        "cursor_dir_custom": saved,
        "mcp_json_path": str(mcp_path) if mcp_path else "",
        "cursor_dir_ready": ready,
        "cursor_dir_error": error,
        "latest_backup": latest_backup,
        "latest_backup_name": backups[0]["name"] if backups else "",
        "backups": backups,
        "backups_dir": str(_ensure_backups_dir().resolve()),
    }


def apply_profile_to_cursor_mcp(
    config: ProfileConfig,
    host_port: int | None = None,
) -> dict[str, Any]:
    cfg_dir = resolve_cursor_config_dir()
    mcp_path = cfg_dir / "mcp.json"
    backup_path: Path | None = None

    if mcp_path.is_file():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        backup_path = _backup_path_for_stamp(stamp)
        shutil.copy2(mcp_path, backup_path)
        mcp_data = parse_mcp_json(mcp_path.read_text(encoding="utf-8"))
    else:
        mcp_data = {"mcpServers": {}}

    merged = merge_server(mcp_data, config, host_port, overwrite=True)
    merged_text = format_mcp_json(merged)
    cfg_dir.mkdir(parents=True, exist_ok=True)
    mcp_path.write_text(merged_text, encoding="utf-8")

    merged_cache = PROJECT_ROOT / "data" / "profiles" / config.profile_name / "mcp-merged.json"
    merged_cache.parent.mkdir(parents=True, exist_ok=True)
    merged_cache.write_text(merged_text, encoding="utf-8")

    from packages.kb.indexer.docker_manager import mcp_entry_for_profile

    entry = mcp_entry_for_profile(config, host_port)
    return {
        "mcp_json_path": str(mcp_path),
        "backup_path": str(backup_path) if backup_path else "",
        "backup_name": backup_path.name if backup_path else "",
        "server_name": config.mcp.server_name,
        "url": entry["url"],
        "mcp_json": merged_text,
    }


def remove_servers_from_cursor_mcp(
    server_names: list[str],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Удалить указанные ключи из mcp.json Cursor (с бэкапом)."""
    names = [name for name in server_names if name]
    if not names:
        return {"removed": [], "mcp_json_path": "", "backup_path": "", "backup_name": ""}

    try:
        cfg_dir = resolve_cursor_config_dir()
    except ValueError as exc:
        return {
            "removed": [],
            "mcp_json_path": "",
            "backup_path": "",
            "backup_name": "",
            "error": str(exc),
        }

    mcp_path = cfg_dir / "mcp.json"
    if not mcp_path.is_file():
        return {
            "removed": [],
            "mcp_json_path": str(mcp_path),
            "backup_path": "",
            "backup_name": "",
        }

    mcp_data = parse_mcp_json(mcp_path.read_text(encoding="utf-8"))
    servers = mcp_data.setdefault("mcpServers", {})
    removed = [name for name in names if name in servers]
    if not removed:
        return {
            "removed": [],
            "mcp_json_path": str(mcp_path),
            "backup_path": "",
            "backup_name": "",
        }

    if dry_run:
        return {
            "removed": removed,
            "mcp_json_path": str(mcp_path),
            "backup_path": "",
            "backup_name": "",
            "dry_run": True,
        }

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup_path = _backup_path_for_stamp(stamp)
    shutil.copy2(mcp_path, backup_path)
    for name in removed:
        del servers[name]
    mcp_path.write_text(format_mcp_json(mcp_data), encoding="utf-8")
    return {
        "removed": removed,
        "mcp_json_path": str(mcp_path),
        "backup_path": str(backup_path),
        "backup_name": backup_path.name,
    }


def remove_profile_from_cursor_mcp(config: ProfileConfig) -> dict[str, Any]:
    return remove_servers_from_cursor_mcp([config.mcp.server_name])
