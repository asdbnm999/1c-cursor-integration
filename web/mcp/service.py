"""Бизнес-логика §2: статус, настройки, section ready (ТЗ §6.4, §10)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from web.cursor_mcp import (
    apply_standard_mcp,
    check_mcp_initialize,
    check_server_health,
    get_mcp_status,
    remove_mcp_servers,
    sync_managed_mcp_entries,
)
from web.docker_naming import mcp_stack_name
from web.mcp.constants import (
    RESOURCE_LIMITS_UI,
    RESOURCE_PRESETS,
    SEARXNG_MCP_KEY,
    SEARXNG_SLUG,
    SERVER_UI,
    SYNTAX_MCP_KEY,
    SYNTAX_SLUG,
    default_server_settings,
)
from web.mcp.deploy import (
    compose_logs,
    container_status,
    deploy_server,
    find_orphaned_searxng,
    published_host_port,
)
from web.mcp_compose import (
    compose_needs_regenerate,
    default_compose_dir,
    ensure_secret_key,
    generate_compose,
    mcp_url,
)
from web.mcp.errors_catalog import build_error_help
from web.settings import load_settings, save_settings
from web.system_check import get_docker_status, get_port_registry, is_port_free


def _docker_root() -> Path:
    return Path(load_settings().get("docker", {}).get("root", "~/DockerMCP")).expanduser()


def _default_mcp_port(slug: str) -> int:
    return 8201 if slug == SEARXNG_SLUG else 8203


def _container_published_mcp_port(slug: str, cfg: dict[str, Any]) -> int | None:
    stack = mcp_stack_name(cfg.get("slug", slug))
    if not container_status(stack).get("running"):
        return None
    return published_host_port(stack)


def auto_mcp_port(slug: str, cfg: dict[str, Any]) -> int:
    """Порт с запущенного {slug}-mcp или дефолт 82xx."""
    published = _container_published_mcp_port(slug, cfg)
    if published is not None:
        return published
    return _default_mcp_port(slug)


def resolve_mcp_port(slug: str, cfg: dict[str, Any]) -> tuple[int, bool, int | None, bool]:
    """
    (port, manual, published, mismatch).
    manual=False → порт с контейнера; manual=True → как задал пользователь.
    """
    published = _container_published_mcp_port(slug, cfg)
    manual = bool(cfg.get("host_port_mcp_manual"))
    auto = published if published is not None else _default_mcp_port(slug)
    if manual:
        port = int(cfg.get("host_port_mcp", auto))
        mismatch = published is not None and port != published
        return port, True, published, mismatch
    return auto, False, published, False


def _syntax_hbk_ready(cfg: dict[str, Any]) -> bool:
    hbk = (cfg.get("hbk_path") or "").strip()
    if not hbk:
        return False
    return Path(hbk).expanduser().is_file()


def get_server_cfg(slug: str) -> dict[str, Any]:
    settings = load_settings()
    std = settings.setdefault("mcp", {}).setdefault("standard", {})
    defaults = default_server_settings(slug)
    stored = std.get(slug if slug != SYNTAX_SLUG else "1c-syntax-helper", {})
    merged = {**defaults, **stored}
    if not merged.get("compose_dir"):
        merged["compose_dir"] = str(default_compose_dir(_docker_root(), slug))
    if slug == SEARXNG_SLUG and not merged.get("secret_key"):
        merged["secret_key"] = ensure_secret_key(merged)
    return merged


def save_server_cfg(slug: str, updates: dict[str, Any]) -> dict[str, Any]:
    settings = load_settings()
    std = settings.setdefault("mcp", {}).setdefault("standard", {})
    key = slug if slug != SYNTAX_SLUG else "1c-syntax-helper"
    current = get_server_cfg(slug)
    current.update(updates)
    std[key] = current
    save_settings(settings)
    return current


def _docker_mem_cap_mb() -> int | None:
    docker = get_docker_status()
    mem = docker.get("memory_bytes")
    if mem:
        return max(256, int(mem / (1024 * 1024)))
    return None


def check_ports_for_server(slug: str, cfg: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    mcp_port, _, _, _ = resolve_mcp_port(slug, cfg)
    if slug == SEARXNG_SLUG:
        ports = {
            mcp_port: "MCP",
            int(cfg.get("host_port_core", 8202)): "Core",
        }
    else:
        ports = {mcp_port: "MCP"}
    for port, role in ports.items():
        free = is_port_free(port)
        issues.append({"port": port, "role": role, "free": free})
    return issues


def find_port_deploy_conflicts(server: str, cfg: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Порты, занятые чужим процессом (не текущим контейнером этого стека)."""
    cfg = cfg or get_server_cfg(server)
    stack = mcp_stack_name(cfg.get("slug", server))
    container = container_status(stack)
    own_ports: set[int] = set()
    if container.get("running"):
        mcp_port, _, published_port, _ = resolve_mcp_port(server, cfg)
        own_ports.add(int(mcp_port))
        if published_port:
            own_ports.add(int(published_port))
        if server == SEARXNG_SLUG:
            own_ports.add(int(cfg.get("host_port_core", 8202)))

    conflicts: list[dict[str, Any]] = []
    for item in check_ports_for_server(server, cfg):
        if item.get("free"):
            continue
        if int(item["port"]) in own_ports:
            continue
        conflicts.append(item)
    return conflicts


def _server_operational(srv: dict[str, Any]) -> bool:
    """Сервер реально работает и прописан в mcp.json с актуальным URL."""
    container = srv.get("container") or {}
    return bool(
        container.get("running")
        and container.get("health") in ("healthy", "none")
        and srv.get("in_mcp_json")
        and srv.get("mcp_json_url") == srv.get("mcp_url")
    )


def _server_has_progress(srv: dict[str, Any]) -> bool:
    if _server_operational(srv):
        return True
    container = srv.get("container") or {}
    if container.get("running") or srv.get("in_mcp_json"):
        return True
    if srv.get("compose_exists") or srv.get("deployed"):
        return True
    return bool((srv.get("compose_dir") or "").strip())


def compute_section_status(payload: dict[str, Any] | None = None) -> str:
    """
    §6.4 §2: ready = оба стандартных MCP (SearXNG + Syntax) Up, healthy и в mcp.json.
    Частичная настройка → in_progress; ничего не трогали → not_started.
    """
    data = payload or get_standard_mcp_status()
    by_slug = {s.get("slug"): s for s in data.get("servers", [])}
    standard = [by_slug.get(slug, {"slug": slug}) for slug in (SEARXNG_SLUG, SYNTAX_SLUG)]

    if not any(_server_has_progress(s) for s in standard):
        return "not_started"
    if all(_server_operational(s) for s in standard):
        return "ready"
    return "in_progress"


def update_section_status() -> str:
    status = compute_section_status()
    settings = load_settings()
    settings.setdefault("sections", {})["mcp"] = status
    save_settings(settings)
    return status


def get_standard_mcp_status(*, with_health: bool = True) -> dict[str, Any]:
    sync_managed_mcp_entries()
    settings = load_settings()
    mcp_cfg = get_mcp_status(with_health=with_health)
    servers_out = []

    for slug in (SEARXNG_SLUG, SYNTAX_SLUG):
        cfg = get_server_cfg(slug)
        ui = SERVER_UI[slug]
        mcp_key = ui["mcp_key"]
        stack = mcp_stack_name(cfg.get("slug", slug))
        port, port_manual, published_port, port_mismatch = resolve_mcp_port(slug, cfg)
        url = mcp_url(port)
        container = container_status(stack)
        in_json = mcp_key in mcp_cfg.get("servers", {})
        json_url = mcp_cfg.get("servers", {}).get(mcp_key, {}).get("url", "")
        health = mcp_cfg.get("servers", {}).get(mcp_key, {}) if with_health and in_json else {}
        health_ok = health.get("health") == "ok" if with_health and in_json else False
        url_match = json_url == url if in_json else False

        ready = (
            container.get("running")
            and (container.get("health") in ("healthy", "none") or health_ok)
            and in_json
            and url_match
            and (health_ok or not with_health)
        )

        servers_out.append(
            {
                "slug": slug,
                "title": ui["title"],
                "why": ui["why"],
                "tools": ui["tools"],
                "mcp_key": mcp_key,
                "deployed": bool(cfg.get("deployed")),
                "stack_name": stack,
                "compose_dir": cfg.get("compose_dir"),
                "host_port_mcp": port,
                "host_port_mcp_manual": port_manual,
                "host_port_published": published_port,
                "port_mismatch": port_mismatch,
                "host_port_core": cfg.get("host_port_core"),
                "hbk_path": cfg.get("hbk_path", ""),
                "mcp_url": url,
                "container": container,
                "in_mcp_json": in_json,
                "mcp_json_url": json_url,
                "health": health,
                "ready": ready,
                "ports": check_ports_for_server(slug, cfg),
                "resource_preset": cfg.get("resource_preset", "economical"),
                "resources": cfg.get("resources") or RESOURCE_PRESETS["economical"],
                "secret_key_set": bool(cfg.get("secret_key")),
                "needs_hbk": slug == SYNTAX_SLUG and not _syntax_hbk_ready(cfg),
                "compose_exists": Path(cfg.get("compose_dir", "")).expanduser().joinpath(
                    "docker-compose.yml"
                ).is_file(),
            }
        )

    docker = get_docker_status()
    section = compute_section_status({"servers": servers_out})

    return {
        "section_status": section,
        "docker": docker,
        "mcp_config": mcp_cfg,
        "servers": servers_out,
        "resource_presets": RESOURCE_PRESETS,
        "resource_limits": RESOURCE_LIMITS_UI,
        "port_registry": get_port_registry(),
        "legacy_compose": docker.get("legacy_compose_detected"),
        "legacy_compose_path": docker.get("legacy_compose_path"),
    }


def apply_mcp_for_enabled(*, dry_run: bool = False) -> dict[str, Any]:
    urls: dict[str, str] = {}
    warnings: list[str] = []
    for slug in (SEARXNG_SLUG, SYNTAX_SLUG):
        cfg = get_server_cfg(slug)
        stack = mcp_stack_name(cfg.get("slug", slug))
        if not container_status(stack).get("running"):
            continue
        port, manual, published, mismatch = resolve_mcp_port(slug, cfg)
        if mismatch and published is not None:
            msg = (
                f"Порт MCP в настройках ({port}) не совпадает с контейнером ({published}). "
                "Остановите стек, нажмите Deploy — затем снова «Применить в mcp.json»."
            )
            return {
                "ok": False,
                "message": msg,
                "diff": "",
                "warnings": [msg],
                "urls": {},
            }
        key = SEARXNG_MCP_KEY if slug == SEARXNG_SLUG else SYNTAX_MCP_KEY
        urls[key] = mcp_url(port)

    if not urls:
        return {
            "ok": False,
            "message": "Нет запущенных серверов — сначала Deploy",
            "diff": "",
            "warnings": [],
        }

    merged, diff = apply_standard_mcp(urls, dry_run=dry_run)
    health_checks: dict[str, Any] = {}
    if not dry_run:
        for key, url in urls.items():
            checked = check_mcp_initialize(url)
            if checked.get("health") != "ok":
                checked = check_server_health(url)
            health_checks[key] = checked
            if checked.get("health") != "ok":
                return {
                    "ok": False,
                    "message": f"MCP «{key}» не отвечает по {url}: {checked.get('detail', 'нет ответа')}",
                    "urls": urls,
                    "diff": diff,
                    "warnings": warnings,
                    "health_checks": health_checks,
                }
        for slug in (SEARXNG_SLUG, SYNTAX_SLUG):
            stack = mcp_stack_name(get_server_cfg(slug).get("slug", slug))
            if container_status(stack).get("running"):
                save_server_cfg(slug, {"deployed": True})
        update_section_status()

    return {
        "ok": True,
        "urls": urls,
        "diff": diff,
        "merged": merged,
        "warnings": warnings,
        "health_checks": health_checks,
    }


def generate_server_compose(server: str, *, regenerate_secret: bool = False) -> dict[str, Any]:
    cfg = get_server_cfg(server)
    port, _, _, _ = resolve_mcp_port(server, cfg)
    cfg = {**cfg, "host_port_mcp": port}
    if regenerate_secret and server == SEARXNG_SLUG:
        import secrets

        cfg["secret_key"] = secrets.token_urlsafe(32)
        save_server_cfg(server, {"secret_key": cfg["secret_key"]})

    target = Path(cfg.get("compose_dir", "")).expanduser()
    result = generate_compose(
        server,
        cfg,
        target_dir=target,
        docker_mem_cap_mb=_docker_mem_cap_mb(),
    )
    save_server_cfg(server, {"compose_dir": str(target), "compose_generated": True})
    return result


def run_deploy(
    server: str,
    *,
    apply_mcp: bool = True,
    dry_run_mcp: bool = False,
    on_progress: Any | None = None,
) -> dict[str, Any]:
    cfg = get_server_cfg(server)
    if server == SYNTAX_SLUG and not _syntax_hbk_ready(cfg):
        hbk_raw = (cfg.get("hbk_path") or "").strip()
        if not hbk_raw:
            return {
                "ok": False,
                "message": "Укажите путь к shcntx_ru.hbk — файл справки обязателен перед Deploy",
            }
        return {
            "ok": False,
            "message": f"Файл shcntx_ru.hbk не найден: {Path(hbk_raw).expanduser()}",
        }

    compose_dir = Path(cfg.get("compose_dir", "")).expanduser()
    slug = cfg.get("slug", server)
    port, _, _, _ = resolve_mcp_port(server, cfg)

    conflicts = find_port_deploy_conflicts(server, cfg)
    if conflicts:
        busy = ", ".join(f"{item['port']} ({item['role']})" for item in conflicts)
        return {
            "ok": False,
            "message": f"Порт занят: {busy}. Освободите порт или измените настройки сервера.",
            "port_conflicts": conflicts,
        }

    if on_progress:
        on_progress("prepare", "start", None)
    compose_file = compose_dir / "docker-compose.yml"
    if compose_needs_regenerate(server, {**cfg, "host_port_mcp": port}, compose_file):
        generate_server_compose(server)
        cfg = get_server_cfg(server)
    if on_progress:
        on_progress("prepare", "done", {"message": "compose готов"})

    deploy_result = deploy_server(
        server,
        compose_dir,
        slug=slug,
        mcp_port=port,
        on_progress=on_progress,
    )
    mcp_apply = None
    if deploy_result.get("ok") and apply_mcp:
        if on_progress:
            on_progress("mcp_apply", "start", None)
        save_server_cfg(server, {"deployed": True})
        mcp_apply = apply_mcp_for_enabled(dry_run=dry_run_mcp)
        if on_progress:
            on_progress(
                "mcp_apply",
                "done" if (mcp_apply or {}).get("ok", True) else "fail",
                mcp_apply or {},
            )
    elif not deploy_result.get("ok"):
        update_section_status()
        return {
            "ok": False,
            "message": deploy_result.get("message") or "Deploy не удался",
            "deploy": deploy_result,
            "mcp_apply": mcp_apply,
        }

    update_section_status()
    return {
        "ok": deploy_result.get("ok", False) and (mcp_apply or {}).get("ok", True),
        "deploy": deploy_result,
        "mcp_apply": mcp_apply,
        "refresh_hint": "Обновите MCP в Cursor (Settings → MCP → Refresh)",
    }


def stop_server(server: str) -> dict[str, Any]:
    """Остановить контейнеры без удаления (docker compose stop)."""
    from web.mcp.deploy import compose_stop

    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return {"ok": False, "message": "Неизвестный сервер"}

    cfg = get_server_cfg(server)
    compose_dir = Path(cfg.get("compose_dir", "")).expanduser()
    if not compose_dir.is_dir():
        return {"ok": False, "message": "Каталог compose не найден"}
    result = compose_stop(compose_dir)
    update_section_status()
    return result


def remove_server(server: str) -> dict[str, Any]:
    """Удалить контейнеры (docker compose down) и убрать запись из mcp.json."""
    from web.mcp.deploy import compose_down

    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return {"ok": False, "message": "Неизвестный сервер"}

    cfg = get_server_cfg(server)
    compose_dir = Path(cfg.get("compose_dir", "")).expanduser()
    if not compose_dir.is_dir():
        return {"ok": False, "message": "Каталог compose не найден"}
    result = compose_down(compose_dir)
    if result.get("ok"):
        mcp_key = SERVER_UI[server]["mcp_key"]
        result["mcp_remove"] = remove_mcp_servers([mcp_key])
    update_section_status()
    return result


def get_logs(server: str, *, tail: int = 100) -> dict[str, Any]:
    cfg = get_server_cfg(server)
    compose_dir = Path(cfg.get("compose_dir", "")).expanduser()
    if not compose_dir.is_dir():
        return {"ok": False, "logs": "", "message": "Каталог compose не найден"}
    text = compose_logs(compose_dir, tail=tail)
    return {"ok": True, "logs": text, "server": server}


def get_errors_help(server: str, *, tail: int = 100) -> dict[str, Any]:
    logs_payload = get_logs(server, tail=tail)
    return build_error_help(server, logs_payload.get("logs", ""))


def update_settings_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """PUT /mcp/api/settings — частичное обновление."""
    server = payload.get("server")
    if server not in (SEARXNG_SLUG, SYNTAX_SLUG):
        return {"ok": False, "message": "server должен быть searxng или 1c-syntax-helper"}

    allowed = {
        "enabled",
        "slug",
        "compose_dir",
        "host_port_mcp",
        "host_port_core",
        "hbk_path",
        "resource_preset",
        "resources",
        "use_external_volumes",
        "secret_key",
    }
    updates = {k: v for k, v in payload.items() if k in allowed}
    if payload.get("host_port_mcp_user_edit"):
        updates["host_port_mcp"] = int(payload["host_port_mcp"])
        updates["host_port_mcp_manual"] = True
    else:
        updates.pop("host_port_mcp", None)
    if updates.get("resource_preset") in RESOURCE_PRESETS:
        preset = updates["resource_preset"]
        updates["resources"] = deepcopy(RESOURCE_PRESETS[preset])

    cfg = save_server_cfg(server, updates)
    conflicts = [p for p in check_ports_for_server(server, cfg) if not p["free"]]
    return {
        "ok": True,
        "server": server,
        "config": cfg,
        "port_conflicts": conflicts,
        "section_status": update_section_status(),
    }
