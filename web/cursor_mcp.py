"""Единый merge mcp.json для Cursor (ТЗ §8)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from web.paths import MCP_BACKUPS_DIR
from web.settings import load_cursor_settings

HEALTH_TIMEOUT_SEC = 3.0


def default_mcp_config_path() -> Path:
    """Типичный путь mcp.json Cursor на текущей ОС."""
    home = Path.home()
    candidates = [
        home / ".cursor" / "mcp.json",
        home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "mcp.json",
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def resolve_mcp_config_path() -> Path:
    """Путь mcp.json: override из cursor-settings или автоопределение."""
    override = load_cursor_settings().get("mcp_config_path", "").strip()
    if override:
        return Path(override).expanduser()
    return default_mcp_config_path()


def read_mcp_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or resolve_mcp_config_path()
    if not config_path.exists():
        return {"mcpServers": {}}
    with config_path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if "mcpServers" not in data:
        data["mcpServers"] = {}
    return data


def merge_servers(
    current: dict[str, Any],
    updates: dict[str, dict[str, Any]],
    *,
    replace_keys: set[str] | None = None,
) -> dict[str, Any]:
    """Не затирает чужие серверы; обновляет только указанные ключи."""
    result = json.loads(json.dumps(current))
    servers = result.setdefault("mcpServers", {})
    replace = replace_keys or set(updates.keys())
    for key, value in updates.items():
        if key in replace:
            servers[key] = value
    return result


def preview_diff(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Текстовый preview diff перед записью mcp.json."""
    before_text = json.dumps(before, ensure_ascii=False, indent=2)
    after_text = json.dumps(after, ensure_ascii=False, indent=2)
    if before_text == after_text:
        return "Изменений нет."
    lines = ["--- mcp.json (текущий)", "+++ mcp.json (после применения)", ""]
    lines.append(before_text)
    lines.append("")
    lines.append("→")
    lines.append("")
    lines.append(after_text)
    return "\n".join(lines)


def backup_mcp_config(path: Path, *, ttl_days: int = 3) -> Path | None:
    """Бэкап mcp.json в data/cursor-mcp-backups/, TTL по умолчанию 3 дня."""
    if not path.exists():
        return None
    MCP_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = MCP_BACKUPS_DIR / f"mcp-{stamp}.json"
    shutil.copy2(path, backup_path)
    _purge_old_backups(ttl_days)
    return backup_path


def _purge_old_backups(ttl_days: int) -> None:
    if not MCP_BACKUPS_DIR.exists():
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    for item in MCP_BACKUPS_DIR.glob("mcp-*.json"):
        mtime = datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc)
        if mtime < cutoff:
            item.unlink(missing_ok=True)


def apply_standard_mcp(
    servers: dict[str, str],
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], str]:
    """Применить стандартные MCP (§2): keys → URL."""
    target = config_path or resolve_mcp_config_path()
    current = read_mcp_config(target)
    updates = {key: {"url": url} for key, url in servers.items()}
    merged = merge_servers(current, updates, replace_keys=set(updates.keys()))
    diff = preview_diff(current, merged)
    if not dry_run:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup_mcp_config(target)
        with target.open("w", encoding="utf-8") as fh:
            json.dump(merged, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return merged, diff


def apply_kb_profile(
    profile_name: str,
    url: str,
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> tuple[dict[str, Any], str]:
    """Добавить/обновить MCP профиля KB (§3)."""
    key = f"1c-kb-{profile_name}"
    return apply_standard_mcp({key: url}, config_path=config_path, dry_run=dry_run)


def remove_mcp_servers(
    keys: list[str] | set[str],
    *,
    config_path: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Удалить указанные MCP-серверы из mcp.json (с бэкапом)."""
    names = [key for key in keys if key]
    if not names:
        return {"removed": [], "config_path": "", "backup_path": None}

    target = config_path or resolve_mcp_config_path()
    current = read_mcp_config(target)
    servers = current.get("mcpServers", {})
    removed = [name for name in names if name in servers]
    if not removed:
        return {"removed": [], "config_path": str(target), "backup_path": None}

    if dry_run:
        return {"removed": removed, "config_path": str(target), "backup_path": None, "dry_run": True}

    backup_path = backup_mcp_config(target) if target.exists() else None
    for name in removed:
        del servers[name]
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as fh:
        json.dump(current, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return {"removed": removed, "config_path": str(target), "backup_path": str(backup_path) if backup_path else None}


def collect_orphan_mcp_keys(config_path: Path | None = None) -> list[str]:
    """
    Ключи в mcp.json без соответствующего контейнера.
    Остановленный, но существующий контейнер не считается осиротевшим.
    """
    from web.docker_naming import mcp_stack_name
    from web.mcp.constants import SEARXNG_SLUG, SERVER_UI, SYNTAX_SLUG
    from web.mcp.deploy import container_status

    target = config_path or resolve_mcp_config_path()
    current = read_mcp_config(target)
    servers = current.get("mcpServers", {})
    if not servers:
        return []

    from web.settings import load_settings

    std_settings = load_settings().get("mcp", {}).get("standard", {})
    orphans: list[str] = []
    for slug in (SEARXNG_SLUG, SYNTAX_SLUG):
        mcp_key = SERVER_UI[slug]["mcp_key"]
        if mcp_key not in servers:
            continue
        cfg_key = "1c-syntax-helper" if slug == SYNTAX_SLUG else slug
        cfg_slug = std_settings.get(cfg_key, {}).get("slug", slug)
        stack = mcp_stack_name(cfg_slug)
        if container_status(stack).get("health") == "missing":
            orphans.append(mcp_key)

    try:
        from packages.kb.indexer.config import load_config
        from packages.kb.indexer.docker_manager import container_exists
        from packages.kb.indexer.profiles import list_profiles
    except Exception:
        return orphans

    known_kb_keys: set[str] = set()
    for profile_name in list_profiles():
        if profile_name == "_template":
            continue
        try:
            config = load_config(profile_name)
        except Exception:
            continue
        key = config.mcp.server_name
        known_kb_keys.add(key)
        if key not in servers:
            continue
        if not container_exists(profile_name):
            orphans.append(key)

    for key in servers:
        if not key.startswith("1c-kb-"):
            continue
        if key in known_kb_keys:
            continue
        orphans.append(key)

    return sorted(set(orphans))


def sync_managed_mcp_entries(*, config_path: Path | None = None) -> list[str]:
    """Убрать из mcp.json записи управляемых MCP без контейнера."""
    orphans = collect_orphan_mcp_keys(config_path)
    if orphans:
        remove_mcp_servers(orphans, config_path=config_path)
    return orphans


def _origin_from_url(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return url.rstrip("/")
    return f"{parsed.scheme}://{parsed.netloc}"


def check_server_health(url: str, *, timeout: float = HEALTH_TIMEOUT_SEC) -> dict[str, Any]:
    """
    HTTP health-check MCP endpoint.
    Пробует /health на origin, затем HEAD/GET на URL.
    """
    if not url:
        return {"health": "unknown", "detail": "URL не задан", "latency_ms": None}

    origin = _origin_from_url(url)
    health_url = urljoin(origin + "/", "health")
    attempts: list[tuple[str, str]] = [
        ("GET", health_url),
        ("GET", url),
        ("HEAD", url),
    ]

    last_error = ""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        for method, target in attempts:
            try:
                start = datetime.now(timezone.utc)
                if method == "GET":
                    resp = client.get(target)
                else:
                    resp = client.head(target)
                latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
                if resp.status_code < 400:
                    body_hint = ""
                    if method == "GET" and "health" in target:
                        text = (resp.text or "")[:200]
                        if "healthy" in text.lower():
                            body_hint = " (healthy)"
                    return {
                        "health": "ok",
                        "detail": f"{method} {target} → {resp.status_code}{body_hint}",
                        "latency_ms": latency,
                    }
                if resp.status_code in (405, 406):
                    return {
                        "health": "ok",
                        "detail": f"{method} {target} → {resp.status_code} (endpoint доступен)",
                        "latency_ms": latency,
                    }
                last_error = f"{method} {target} → HTTP {resp.status_code}"
            except httpx.TimeoutException:
                last_error = f"Таймаут {target}"
            except httpx.RequestError as exc:
                last_error = f"{target}: {exc}"

    return {"health": "unreachable", "detail": last_error or "нет ответа", "latency_ms": None}


def check_mcp_initialize(url: str, *, timeout: float = HEALTH_TIMEOUT_SEC) -> dict[str, Any]:
    """Проверка MCP так же, как Cursor: POST initialize + Accept streamable HTTP."""
    if not url:
        return {"health": "unknown", "detail": "URL не задан", "latency_ms": None}

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "1c-cursor", "version": "1"},
        },
    }
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            start = datetime.now(timezone.utc)
            resp = client.post(
                url,
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
            latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
            body = resp.text or ""
            if resp.status_code < 400 and '"result"' in body and "serverInfo" in body:
                return {
                    "health": "ok",
                    "detail": "MCP initialize OK",
                    "latency_ms": latency,
                }
            if resp.status_code < 400:
                return {
                    "health": "error",
                    "detail": f"initialize → HTTP {resp.status_code}: {body[:200]}",
                    "latency_ms": latency,
                }
            return {
                "health": "unreachable",
                "detail": f"initialize → HTTP {resp.status_code}: {body[:200]}",
                "latency_ms": latency,
            }
    except httpx.TimeoutException:
        return {"health": "unreachable", "detail": f"Таймаут {url}", "latency_ms": None}
    except httpx.RequestError as exc:
        return {"health": "unreachable", "detail": f"{url}: {exc}", "latency_ms": None}


def get_mcp_status(
    config_path: Path | None = None,
    *,
    with_health: bool = False,
) -> dict[str, Any]:
    """Статус MCP-серверов из mcp.json."""
    target = config_path or resolve_mcp_config_path()
    current = read_mcp_config(target)
    servers: dict[str, Any] = {}
    for name, entry in current.get("mcpServers", {}).items():
        url = entry.get("url", "")
        item = {"url": url, "health": "unknown", "detail": "", "latency_ms": None}
        if with_health and url:
            checked = check_server_health(url)
            item.update(checked)
        servers[name] = item

    summary = "empty"
    if servers:
        states = [s.get("health", "unknown") for s in servers.values()]
        if with_health:
            if all(s == "ok" for s in states):
                summary = "all_ok"
            elif any(s == "ok" for s in states):
                summary = "partial"
            elif any(s == "unreachable" for s in states):
                summary = "unreachable"
            else:
                summary = "unknown"
        else:
            summary = "configured"

    return {
        "config_path": str(target),
        "config_exists": target.exists(),
        "summary": summary,
        "servers": servers,
    }


def check_all_mcp_servers(config_path: Path | None = None) -> dict[str, Any]:
    """Ping всех серверов из mcp.json."""
    return get_mcp_status(config_path, with_health=True)
