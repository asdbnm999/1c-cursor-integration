from __future__ import annotations

import os
import subprocess
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.docker_names import CONTAINER_PORT, container_name, image_name
from packages.kb.paths import PROJECT_ROOT

COMPOSE_FILENAME = "docker-compose.yml"
DEFAULT_MEM_LIMIT_MB = 1024
KB_MEM_LIMIT_UI = {"min": 512, "max": 8192, "default": DEFAULT_MEM_LIMIT_MB}


def kb_mcp_folder_name(profile_name: str) -> str:
    return f"1c-kb-{profile_name}"


def default_compose_dir(profile_name: str) -> Path:
    return Path.home() / "DockerMCP" / kb_mcp_folder_name(profile_name)


def resolve_mcp_compose_dir(picked: str | Path, profile_name: str) -> Path:
    """Родительский каталог → …/1c-kb-<profile>; уже выбранная подпапка — без вложения."""
    path = Path(picked).expanduser().resolve()
    expected = kb_mcp_folder_name(profile_name)
    if path.name == expected:
        return path
    return path / expected


def compose_project_name(profile_name: str) -> str:
    return f"1c-kb-{profile_name}-mcp"


def compose_file_path(compose_dir: Path) -> Path:
    return compose_dir / COMPOSE_FILENAME


def mem_limit_mb_for_config(config: ProfileConfig) -> int:
    """Лимит RAM контейнера MCP: профиль → глобальный settings.kb → дефолт."""
    profile_limit = int(getattr(config.docker, "mem_limit_mb", 0) or 0)
    if profile_limit > 0:
        return profile_limit
    try:
        from web.settings import load_settings

        kb_cfg = load_settings().get("kb") or {}
        value = kb_cfg.get("container_mem_limit_mb")
        if isinstance(value, (int, float)) and value > 0:
            return int(value)
    except Exception:
        pass
    return DEFAULT_MEM_LIMIT_MB


def _gpu_deploy_block(config: ProfileConfig) -> str:
    use_gpu = config.docker.gpu or os.environ.get("KB_DOCKER_GPU", "").strip() in {"1", "true", "yes"}
    if not use_gpu:
        return ""
    return """
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
"""


def render_compose_yaml(config: ProfileConfig) -> str:
    profile_name = config.profile_name
    host_port = config.mcp.port
    project_root = PROJECT_ROOT.resolve()
    cname = container_name(profile_name)
    img = image_name(profile_name)
    project = compose_project_name(profile_name)
    gpu_block = _gpu_deploy_block(config)
    mem_limit = mem_limit_mb_for_config(config)

    return f"""# 1C Knowledge Base MCP — профиль {profile_name}
# Сгенерировано 1C:Cursor. Образ собирается отдельно (кнопка «Собрать образ»).
#
# Запуск:  docker compose up -d
# MCP URL: http://127.0.0.1:{host_port}/mcp

name: {project}

services:
  {cname}:
    container_name: {cname}
    image: {img}
    restart: unless-stopped
    ports:
      - "{host_port}:{CONTAINER_PORT}"
    environment:
      KB_PROFILE: {profile_name}
      HF_HOME: /app/data/hf_cache
    volumes:
      - {project_root / "data"}:/app/data
      - {project_root / "profiles"}:/app/profiles:ro
    mem_limit: {mem_limit}m
    healthcheck:
      test: ["CMD", "python", "-c", "import socket; s=socket.socket(); s.settimeout(3); s.connect(('127.0.0.1', {CONTAINER_PORT})); s.close()"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 90s{gpu_block}
"""


def write_compose_file(compose_dir: Path, config: ProfileConfig) -> Path:
    compose_dir = compose_dir.expanduser().resolve()
    compose_dir.mkdir(parents=True, exist_ok=True)
    path = compose_file_path(compose_dir)
    path.write_text(render_compose_yaml(config), encoding="utf-8")
    return path


def _compose_cmd(compose_dir: Path, profile_name: str, *args: str) -> list[str]:
    compose_dir = compose_dir.expanduser().resolve()
    compose_path = compose_file_path(compose_dir)
    if not compose_path.exists():
        raise FileNotFoundError(f"Compose-файл не найден: {compose_path}")
    return [
        "docker",
        "compose",
        "-f",
        str(compose_path),
        "-p",
        compose_project_name(profile_name),
        *args,
    ]


def _run_compose(
    compose_dir: Path,
    profile_name: str,
    *args: str,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    cmd = _compose_cmd(compose_dir, profile_name, *args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def compose_up(compose_dir: Path, config: ProfileConfig, *, rebuild: bool = False) -> str:
    write_compose_file(compose_dir, config)
    args = ["up", "-d"]
    if rebuild:
        args.append("--pull")
        args.append("missing")
    result = _run_compose(compose_dir, config.profile_name, *args, timeout=600)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise RuntimeError(output or "docker compose up завершился с ошибкой")
    return output


def compose_stop(compose_dir: Path, profile_name: str) -> str:
    compose_path = compose_file_path(compose_dir)
    if not compose_path.exists():
        return ""
    result = _run_compose(compose_dir, profile_name, "stop", timeout=120)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise RuntimeError(output or "docker compose stop завершился с ошибкой")
    return output


def compose_down(compose_dir: Path, profile_name: str) -> str:
    compose_path = compose_file_path(compose_dir)
    if not compose_path.exists():
        return ""
    result = _run_compose(compose_dir, profile_name, "down", timeout=120)
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise RuntimeError(output or "docker compose down завершился с ошибкой")
    return output


def compose_logs(compose_dir: Path, profile_name: str, tail: int = 300) -> str:
    compose_path = compose_file_path(compose_dir)
    if not compose_path.exists():
        return ""
    result = _run_compose(
        compose_dir,
        profile_name,
        "logs",
        "--tail",
        str(tail),
        timeout=30,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode != 0:
        return output or f"docker compose logs завершился с кодом {result.returncode}"
    return output or "(контейнер пока не писал в stdout/stderr — это нормально для MCP-сервера в ожидании)"
