"""Генерация docker-compose и сопутствующих файлов для §2 (ТЗ §10.3–10.5)."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import yaml

from web.docker_naming import auxiliary_name, mcp_stack_name
from web.mcp.constants import (
    DEFAULT_PORT_SEARXNG_CORE,
    DEFAULT_PORT_SEARXNG_MCP,
    DEFAULT_PORT_SYNTAX_MCP,
    EXTERNAL_VOLUMES,
    RESOURCE_PRESETS,
    SEARXNG_SLUG,
    SYNTAX_SLUG,
    SYNTAX_REPO_DIRNAME,
)

DEFAULT_HOST = "127.0.0.1"


def mcp_url(host_port: int) -> str:
    return f"http://{DEFAULT_HOST}:{host_port}/mcp"


def _mem_limit(value_mb: int) -> str:
    return f"{int(value_mb)}m"


def resolve_resources(cfg: dict[str, Any], preset: str | None = None) -> dict[str, int]:
    name = preset or cfg.get("resource_preset", "economical")
    if name in RESOURCE_PRESETS:
        base = dict(RESOURCE_PRESETS[name])
    else:
        base = dict(RESOURCE_PRESETS["economical"])
    overrides = cfg.get("resources") or {}
    for key, val in overrides.items():
        if isinstance(val, (int, float)):
            base[key] = int(val)
    return base


def default_compose_dir(docker_root: Path, slug: str) -> Path:
    sub = "searxng" if slug == SEARXNG_SLUG else "1c-syntax"
    return docker_root.expanduser() / sub


def ensure_secret_key(cfg: dict[str, Any]) -> str:
    key = (cfg.get("secret_key") or "").strip()
    if key:
        return key
    return secrets.token_urlsafe(32)


def generate_searxng_files(
    cfg: dict[str, Any],
    *,
    target_dir: Path,
    docker_mem_cap_mb: int | None = None,
) -> dict[str, Any]:
    """Записать docker-compose.yml, .env, core-config/settings.yml для SearXNG."""
    slug = cfg.get("slug", SEARXNG_SLUG)
    stack = mcp_stack_name(slug)
    valkey = auxiliary_name(slug, "valkey")
    core = auxiliary_name(slug, "core")
    mcp_svc = mcp_stack_name(slug)

    port_mcp = int(cfg.get("host_port_mcp", DEFAULT_PORT_SEARXNG_MCP))
    port_core = int(cfg.get("host_port_core", DEFAULT_PORT_SEARXNG_CORE))
    resources = resolve_resources(cfg)
    secret_key = ensure_secret_key(cfg)

    if docker_mem_cap_mb:
        for key in ("valkey_mem", "core_mem", "searxng_mcp_mem"):
            resources[key] = min(resources[key], docker_mem_cap_mb)

    compose: dict[str, Any] = {
        "name": stack,
        "services": {
            valkey: {
                "container_name": valkey,
                "image": "docker.io/valkey/valkey:9-alpine",
                "command": (
                    "valkey-server --save \"\" --appendonly no "
                    f"--maxmemory {resources['valkey_mem']}mb "
                    "--maxmemory-policy allkeys-lru --loglevel warning"
                ),
                "restart": "unless-stopped",
                "mem_limit": _mem_limit(resources["valkey_mem"]),
                "cpus": 0.25,
            },
            core: {
                "container_name": core,
                "image": "docker.io/searxng/searxng:${SEARXNG_VERSION:-latest}",
                "restart": "unless-stopped",
                "ports": [f"{port_core}:${{SEARXNG_PORT:-8080}}"],
                "env_file": "./.env",
                "volumes": [
                    "./core-config/:/etc/searxng/",
                    "core-data:/var/cache/searxng/",
                ],
                "depends_on": {valkey: {"condition": "service_started"}},
                "mem_limit": _mem_limit(resources["core_mem"]),
                "cpus": 0.75,
            },
            mcp_svc: {
                "container_name": mcp_svc,
                "image": "isokoliuk/mcp-searxng:latest",
                "restart": "unless-stopped",
                "ports": [f"{port_mcp}:{port_mcp}"],
                "environment": {
                    "SEARXNG_URL": f"http://{core}:8080",
                    "MCP_HTTP_PORT": str(port_mcp),
                    "MCP_HTTP_HOST": "0.0.0.0",
                },
                "depends_on": {core: {"condition": "service_started"}},
                "mem_limit": _mem_limit(resources["searxng_mcp_mem"]),
                "cpus": 0.5,
                "healthcheck": {
                    "test": [
                        "CMD-SHELL",
                        f"wget -q -O- http://127.0.0.1:{port_mcp}/health | grep -q healthy",
                    ],
                    "interval": "30s",
                    "timeout": "5s",
                    "retries": 3,
                    "start_period": "10s",
                },
            },
        },
        "volumes": {
            "core-data": (
                {"external": True, "name": EXTERNAL_VOLUMES["searxng_core"]}
                if cfg.get("use_external_volumes", True)
                else {}
            ),
        },
    }

    settings_yml = {
        "use_default_settings": True,
        "search": {"formats": ["html", "json"]},
        "server": {"secret_key": secret_key, "limiter": False},
        "outgoing": {"request_timeout": 10.0},
    }
    env_content = "SEARXNG_VERSION=latest\nSEARXNG_PORT=8080\n"

    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / "core-config").mkdir(exist_ok=True)
    _write_yaml(target_dir / "docker-compose.yml", compose)
    (target_dir / ".env").write_text(env_content, encoding="utf-8")
    _write_yaml(target_dir / "core-config" / "settings.yml", settings_yml)

    return {
        "server": SEARXNG_SLUG,
        "target_dir": str(target_dir),
        "stack_name": stack,
        "mcp_url": mcp_url(port_mcp),
        "secret_key": secret_key,
        "files": ["docker-compose.yml", ".env", "core-config/settings.yml"],
    }


def generate_syntax_files(
    cfg: dict[str, Any],
    *,
    target_dir: Path,
    docker_mem_cap_mb: int | None = None,
) -> dict[str, Any]:
    """Записать docker-compose.yml для 1C Syntax Helper."""
    slug = cfg.get("slug", SYNTAX_SLUG)
    stack = mcp_stack_name(slug)
    es_svc = auxiliary_name(slug, "es")
    mcp_svc = mcp_stack_name(slug)

    port_mcp = int(cfg.get("host_port_mcp", DEFAULT_PORT_SYNTAX_MCP))
    resources = resolve_resources(cfg)
    hbk_path = (cfg.get("hbk_path") or "").strip()

    if docker_mem_cap_mb:
        for key in ("es_mem", "syntax_mcp_mem", "es_heap"):
            if key in resources:
                resources[key] = min(resources[key], docker_mem_cap_mb)

    hbk_mount = "./1c-syntax-helper-mcp/data/hbk"
    if hbk_path:
        hbk_file = Path(hbk_path).expanduser().resolve()
        hbk_mount = str(hbk_file.parent)

    compose: dict[str, Any] = {
        "name": stack,
        "x-healthcheck-defaults": {
            "interval": "60s",
            "timeout": "10s",
            "retries": 3,
        },
        "services": {
            es_svc: {
                "container_name": es_svc,
                "image": "docker.elastic.co/elasticsearch/elasticsearch:9.1.0",
                "restart": "unless-stopped",
                "environment": {
                    "discovery.type": "single-node",
                    "xpack.security.enabled": "false",
                    "ES_JAVA_OPTS": f"-Xms{resources['es_heap']}m -Xmx{resources['es_heap']}m",
                    "indices.breaker.total.limit": "40%",
                },
                "volumes": ["es-data:/usr/share/elasticsearch/data"],
                "mem_limit": _mem_limit(resources.get("es_mem", resources["es_heap"] * 2)),
                "cpus": 1.5,
                "healthcheck": {
                    "interval": "60s",
                    "timeout": "10s",
                    "retries": 3,
                    "test": [
                        "CMD-SHELL",
                        "curl -f http://localhost:9200/_cluster/health || exit 1",
                    ],
                    "start_period": "60s",
                },
            },
            mcp_svc: {
                "container_name": mcp_svc,
                "build": f"./{SYNTAX_REPO_DIRNAME}",
                "restart": "unless-stopped",
                "ports": [f"{port_mcp}:8000"],
                "depends_on": {es_svc: {"condition": "service_healthy"}},
                "volumes": [
                    f"{hbk_mount}:/app/data/hbk:ro",
                    f"./{SYNTAX_REPO_DIRNAME}/data/logs:/app/logs",
                ],
                "environment": {
                    "ELASTICSEARCH_HOST": es_svc,
                    "ELASTICSEARCH_PORT": "9200",
                    "LOG_LEVEL": "INFO",
                    "REINDEX_ON_STARTUP": "false",
                },
                "mem_limit": _mem_limit(resources["syntax_mcp_mem"]),
                "cpus": 1.0,
                "healthcheck": {
                    "interval": "60s",
                    "timeout": "10s",
                    "retries": 3,
                    "test": ["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                    "start_period": "120s",
                },
            },
        },
        "volumes": {
            "es-data": (
                {"external": True, "name": EXTERNAL_VOLUMES["syntax_es"]}
                if cfg.get("use_external_volumes", True)
                else {}
            ),
        },
    }

    target_dir.mkdir(parents=True, exist_ok=True)
    _write_yaml(target_dir / "docker-compose.yml", compose)

    return {
        "server": SYNTAX_SLUG,
        "target_dir": str(target_dir),
        "stack_name": stack,
        "mcp_url": mcp_url(port_mcp),
        "hbk_path": hbk_path,
        "hbk_mount": hbk_mount,
        "files": ["docker-compose.yml"],
        "needs_hbk_for_deploy": not bool(hbk_path),
    }


def _write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def compose_needs_regenerate(server: str, cfg: dict[str, Any], compose_path: Path) -> bool:
    """True, если docker-compose.yml отсутствует или не соответствует slug/портам/HBK."""
    if not compose_path.is_file():
        return True
    slug = cfg.get("slug", server)
    mcp_svc = mcp_stack_name(slug)
    try:
        data = yaml.safe_load(compose_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return True
    if not isinstance(data, dict):
        return True
    services = data.get("services") or {}
    if mcp_svc not in services:
        return True

    port_mcp = int(
        cfg.get(
            "host_port_mcp",
            DEFAULT_PORT_SEARXNG_MCP if server == SEARXNG_SLUG else DEFAULT_PORT_SYNTAX_MCP,
        )
    )
    ports = services[mcp_svc].get("ports") or []
    port_prefix = f"{port_mcp}:"
    if not any(str(p).startswith(port_prefix) for p in ports):
        return True

    if server == SYNTAX_SLUG:
        es_svc = auxiliary_name(slug, "es")
        if es_svc not in services:
            return True
        hbk_path = (cfg.get("hbk_path") or "").strip()
        if hbk_path:
            hbk_parent = str(Path(hbk_path).expanduser().resolve().parent)
            vols = services[mcp_svc].get("volumes") or []
            if not any(hbk_parent in str(v) for v in vols):
                return True
    elif server == SEARXNG_SLUG:
        valkey = auxiliary_name(slug, "valkey")
        core = auxiliary_name(slug, "core")
        if valkey not in services or core not in services:
            return True
        port_core = int(cfg.get("host_port_core", DEFAULT_PORT_SEARXNG_CORE))
        core_ports = services[core].get("ports") or []
        if not any(str(p).startswith(f"{port_core}:") for p in core_ports):
            return True

    return False


def generate_compose(
    server: str,
    cfg: dict[str, Any],
    *,
    target_dir: Path | None = None,
    docker_root: Path | None = None,
    docker_mem_cap_mb: int | None = None,
) -> dict[str, Any]:
    root = Path(docker_root or Path.home() / "DockerMCP")
    if target_dir is None:
        target_dir = Path(cfg.get("compose_dir") or default_compose_dir(root, server))
    else:
        target_dir = Path(target_dir)

    if server == SEARXNG_SLUG:
        return generate_searxng_files(cfg, target_dir=target_dir, docker_mem_cap_mb=docker_mem_cap_mb)
    if server == SYNTAX_SLUG:
        return generate_syntax_files(cfg, target_dir=target_dir, docker_mem_cap_mb=docker_mem_cap_mb)
    raise ValueError(f"Неизвестный server: {server}")
