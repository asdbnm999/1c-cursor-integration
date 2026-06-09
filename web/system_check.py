"""Диагностика системы: Python, Docker, RAM, порты (ТЗ §5–§6, §7)."""

from __future__ import annotations

import platform
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any

from web.settings import load_settings

# Каталог портов проекта (ТЗ §7.1)
STANDARD_MCP_PORTS: dict[int, str] = {
    8201: "SearXNG MCP",
    8202: "SearXNG Core",
    8203: "1C Syntax Helper MCP",
}

KB_PORT_BASE = 8301


def get_python_info() -> dict[str, Any]:
    return {
        "version": platform.python_version(),
        "implementation": platform.python_implementation(),
        "executable": sys.executable,
        "ok": sys.version_info >= (3, 11),
    }


def _parse_docker_mem_total(text: str) -> int | None:
    match = re.search(r"Total Memory:\s*([\d.]+)\s*(GiB|MiB|KiB|B)", text)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    multipliers = {"B": 1, "KiB": 1024, "MiB": 1024**2, "GiB": 1024**3}
    return int(value * multipliers.get(unit, 1))


def get_docker_status(docker_root: Path | None = None) -> dict[str, Any]:
    """Состояние Docker CLI/daemon и предупреждение legacy compose."""
    settings = load_settings()
    root = Path(docker_root or settings.get("docker", {}).get("root", "~/DockerMCP")).expanduser()
    legacy_compose = root / "docker-compose.yml"

    result: dict[str, Any] = {
        "installed": False,
        "running": False,
        "message": "",
        "memory_bytes": None,
        "memory_human": "",
        "legacy_compose_detected": legacy_compose.is_file(),
        "legacy_compose_path": str(legacy_compose),
        "docker_root": str(root),
    }

    if not shutil.which("docker"):
        result["message"] = "Docker CLI не найден в PATH"
        return result

    result["installed"] = True
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        result["message"] = f"Ошибка вызова docker: {exc}"
        return result

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        result["message"] = err.splitlines()[0] if err else "Docker daemon недоступен"
        return result

    result["running"] = True
    result["message"] = "Docker daemon работает"
    mem = _parse_docker_mem_total(proc.stdout or "")
    if mem is not None:
        result["memory_bytes"] = mem
        result["memory_human"] = _format_bytes_simple(mem)
    return result


def get_host_memory() -> dict[str, Any]:
    """RAM хоста (macOS/Linux через sysctl/proc; fallback — unknown)."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True, timeout=5)
            total = int(out.strip())
            return {"total_bytes": total, "total_human": _format_bytes_simple(total)}
        if Path("/proc/meminfo").exists():
            meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
            match = re.search(r"MemTotal:\s+(\d+)\s+kB", meminfo)
            if match:
                total = int(match.group(1)) * 1024
                return {"total_bytes": total, "total_human": _format_bytes_simple(total)}
    except (OSError, subprocess.SubprocessError, ValueError):
        pass
    return {"total_bytes": None, "total_human": "неизвестно"}


def _format_bytes_simple(num: int) -> str:
    gib = num / (1024**3)
    return f"{gib:.1f} GiB"


def _is_port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.35) -> bool:
    """Порт занят, если на нём уже отвечает сервис (Docker/MCP)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def is_port_free(port: int, host: str = "127.0.0.1") -> bool:
    if _is_port_listening(port, host):
        return False
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _mcp_json_port_entries() -> dict[int, str]:
    """Порты из ~/.cursor/mcp.json — чтобы реестр совпадал с блоком «Состояние MCP»."""
    from urllib.parse import urlparse

    from web.cursor_mcp import read_mcp_config, resolve_mcp_config_path

    entries: dict[int, str] = {}
    try:
        path = resolve_mcp_config_path()
        cfg = read_mcp_config(path)
    except (OSError, ValueError):
        return entries
    for name, entry in (cfg.get("mcpServers") or {}).items():
        if not isinstance(entry, dict):
            continue
        url = str(entry.get("url") or "").strip()
        if not url:
            continue
        parsed = urlparse(url)
        if not parsed.port:
            continue
        host = (parsed.hostname or "").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            continue
        entries[int(parsed.port)] = f"MCP «{name}» (mcp.json)"
    return entries


def get_port_registry() -> list[dict[str, Any]]:
    """Реестр портов 82xx/83xx проекта + фактическая занятость."""
    settings = load_settings()
    entries: dict[int, str] = dict(STANDARD_MCP_PORTS)

    mcp = settings.get("mcp", {})
    for name, cfg in mcp.get("kb_profiles", {}).items():
        port = cfg.get("host_port")
        if port:
            entries[int(port)] = f"KB профиль «{name}»"

    std = mcp.get("standard", {})
    if std.get("searxng", {}).get("host_port_mcp"):
        entries[int(std["searxng"]["host_port_mcp"])] = "SearXNG MCP (настройки)"
    if std.get("searxng", {}).get("host_port_core"):
        entries[int(std["searxng"]["host_port_core"])] = "SearXNG Core (настройки)"
    if std.get("1c-syntax-helper", {}).get("host_port_mcp"):
        entries[int(std["1c-syntax-helper"]["host_port_mcp"])] = "1C Syntax MCP (настройки)"

    for port, role in _mcp_json_port_entries().items():
        entries.setdefault(port, role)

    result = []
    for port in sorted(entries):
        free = is_port_free(port)
        result.append(
            {
                "port": port,
                "role": entries[port],
                "free": free,
                "status": "free" if free else "in_use",
            }
        )
    return result


def estimate_mcp_ram_mb() -> dict[str, Any]:
    """
    Оценка RAM для включённых MCP-стеков (ТЗ §5.2, §13).
    Суммирует пресеты §2 и по одному контейнеру на профиль KB.
    """
    from web.mcp.constants import RESOURCE_PRESETS
    from web.mcp.service import get_server_cfg
    from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG

    settings = load_settings()
    preset_name = settings.get("mcp", {}).get("resource_preset", "economical")
    preset = RESOURCE_PRESETS.get(preset_name, RESOURCE_PRESETS["economical"])

    breakdown: list[dict[str, Any]] = []
    total_mb = 0

    def _stack_resources(slug: str) -> dict[str, Any]:
        try:
            cfg = get_server_cfg(slug)
            return cfg.get("resources") or preset
        except Exception:
            return preset

    # Стандартные §2 MCP — всегда в оценке RAM (SearXNG + Syntax)
    searxng_res = _stack_resources(SEARXNG_SLUG)
    searxng_mb = (
        int(searxng_res.get("valkey_mem", preset["valkey_mem"]))
        + int(searxng_res.get("core_mem", preset["core_mem"]))
        + int(searxng_res.get("searxng_mcp_mem", preset["searxng_mcp_mem"]))
    )
    breakdown.append({"stack": "SearXNG", "estimate_mb": searxng_mb})
    total_mb += searxng_mb

    syntax_res = _stack_resources(SYNTAX_SLUG)
    syntax_mb = int(syntax_res.get("es_mem", preset["es_mem"])) + int(
        syntax_res.get("syntax_mcp_mem", preset["syntax_mcp_mem"])
    )
    breakdown.append({"stack": "1C Syntax Helper", "estimate_mb": syntax_mb})
    total_mb += syntax_mb

    kb_profiles = settings.get("mcp", {}).get("kb_profiles", {})
    try:
        from packages.kb.indexer.profiles import list_profiles

        from packages.kb.indexer.config import load_config
        from packages.kb.indexer.docker_compose import mem_limit_mb_for_config

        for name in list_profiles():
            try:
                kb_mb = mem_limit_mb_for_config(load_config(name))
            except Exception:
                kb_mb = 512
            breakdown.append({"stack": f"KB «{name}»", "estimate_mb": kb_mb})
            total_mb += kb_mb
    except Exception:
        for name in kb_profiles:
            breakdown.append({"stack": f"KB «{name}»", "estimate_mb": 512})
            total_mb += 512

    docker = get_docker_status()
    docker_cap = None
    if docker.get("memory_bytes"):
        docker_cap = int(docker["memory_bytes"] / (1024 * 1024))

    host = get_host_memory()
    host_mb = None
    if host.get("total_bytes"):
        host_mb = int(host["total_bytes"] / (1024 * 1024))

    warning = None
    if docker_cap and total_mb > docker_cap * 0.85:
        warning = (
            f"Оценка {total_mb} MiB близка к лимиту Docker ({docker_cap} MiB). "
            "Расширьте ресурсы Docker Desktop или уменьшите пресет."
        )
    elif total_mb == 0:
        warning = None

    return {
        "preset": preset_name,
        "total_mb": total_mb,
        "breakdown": breakdown,
        "docker_limit_mb": docker_cap,
        "host_ram_mb": host_mb,
        "warning": warning,
    }


def run_system_diagnostics() -> dict[str, Any]:
    docker = get_docker_status()
    ram = estimate_mcp_ram_mb()
    warnings = _collect_warnings(docker)
    if ram.get("warning"):
        warnings.append(ram["warning"])
    return {
        "python": get_python_info(),
        "docker": docker,
        "memory": get_host_memory(),
        "ram_estimate": ram,
        "ports": get_port_registry(),
        "warnings": warnings,
    }


def _collect_warnings(docker: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not docker.get("running"):
        warnings.append(
            "Docker daemon недоступен. Разделы §2 и §3 (MCP/KB) требуют Docker Desktop или Docker Engine."
        )
    if docker.get("legacy_compose_detected"):
        warnings.append(
            f"Обнаружен устаревший {docker.get('legacy_compose_path')}. "
            "Используйте отдельные каталоги searxng/ и 1c-syntax/ (ТЗ §5.1)."
        )
    busy = [p for p in get_port_registry() if not p["free"]]
    if busy:
        ports = ", ".join(str(p["port"]) for p in busy)
        warnings.append(f"Заняты порты проекта: {ports}. Проверьте конфликты перед deploy.")
    return warnings
