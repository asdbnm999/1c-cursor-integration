from __future__ import annotations

import logging
import subprocess
from dataclasses import dataclass
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.docker_compose import compose_down, compose_logs, compose_stop, compose_up
from packages.kb.indexer.docker_names import CONTAINER_PORT, container_name, image_name
from packages.kb.indexer.profile_ops import save_compose_dir
from packages.kb.indexer.profiles import PROJECT_ROOT

logger = logging.getLogger(__name__)


@dataclass
class ContainerStatus:
    profile_name: str
    running: bool
    container_id: str = ""
    host_port: int = 0
    url: str = ""
    compose_dir: str = ""
    error: str = ""
    port_auto_assigned: bool = False
    previous_port: int | None = None


def _get_client():
    try:
        import docker
    except ImportError as exc:
        raise RuntimeError("Установите пакет docker: pip install docker") from exc
    return docker.from_env()


def mcp_url(host_port: int) -> str:
    return f"http://127.0.0.1:{host_port}/mcp"


def _resolve_compose_dir(config: ProfileConfig) -> Path:
    if not config.docker.compose_dir:
        raise ValueError(
            "Не указана директория Docker Compose. "
            "Выберите каталог при запуске контейнера (например ~/DockerMCP/1c-kb-<профиль>)."
        )
    return Path(config.docker.compose_dir).expanduser().resolve()


def build_image(profile_name: str, force: bool = False) -> str:
    from packages.kb.indexer.docker_build import (
        image_exists,
        run_docker_build_cli,
        tag_profile_image,
    )
    from packages.kb.indexer.docker_wheels import ensure_kb_mcp_wheels

    profile_image = image_name(profile_name)
    if not force and image_exists(profile_name):
        return profile_image

    logger.info("Сборка общего Docker-образа KB MCP для профиля %s…", profile_name)
    ensure_kb_mcp_wheels(force=force, log=logger.info)
    run_docker_build_cli(log=logger.info)
    return tag_profile_image(profile_name)


def container_exists(profile_name: str) -> bool:
    try:
        _get_client().containers.get(container_name(profile_name))
        return True
    except Exception:
        return False


def get_status(profile_name: str) -> ContainerStatus:
    config = load_config(profile_name)
    name = container_name(profile_name)
    compose_dir = config.docker.compose_dir
    try:
        client = _get_client()
        container = client.containers.get(name)
        running = container.status == "running"
        host_port = config.mcp.port
        for item in container.attrs.get("NetworkSettings", {}).get("Ports", {}).get(f"{CONTAINER_PORT}/tcp", []) or []:
            if item.get("HostPort"):
                host_port = int(item["HostPort"])
                break
        return ContainerStatus(
            profile_name=profile_name,
            running=running,
            container_id=container.short_id,
            host_port=host_port,
            url=mcp_url(host_port) if running else "",
            compose_dir=compose_dir,
        )
    except Exception:
        return ContainerStatus(
            profile_name=profile_name,
            running=False,
            host_port=config.mcp.port,
            compose_dir=compose_dir,
        )


def start_container(
    profile_name: str,
    *,
    compose_dir: str | Path | None = None,
    rebuild: bool = False,
    recreate: bool = False,
) -> ContainerStatus:
    if compose_dir:
        save_compose_dir(profile_name, compose_dir)

    from packages.kb.indexer.docker_build import image_exists
    from packages.kb.indexer.kb_ports import ensure_profile_host_port

    if rebuild:
        logger.warning(
            "Параметр rebuild устарел для docker/start — используйте сборку через docker/build "
            "или кнопку «Запустить MCP» в интерфейсе.",
        )
    if not image_exists(profile_name):
        raise ValueError(
            "Docker-образ не найден. Дождитесь завершения сборки "
            "или включите «Пересобрать образ» и нажмите «Запустить MCP».",
        )

    current = get_status(profile_name)
    port_auto_assigned = False
    previous_port: int | None = None
    if not current.running:
        config = load_config(profile_name)
        previous_port = config.mcp.port
        _new_port, port_auto_assigned = ensure_profile_host_port(profile_name)

    config = load_config(profile_name)
    compose_path = _resolve_compose_dir(config)

    logger.info("Запуск compose-проекта в %s", compose_path)
    compose_up(compose_path, config, rebuild=False, recreate=recreate)
    status = get_status(profile_name)
    status.port_auto_assigned = port_auto_assigned
    status.previous_port = previous_port if port_auto_assigned else None
    return status


def stop_container(profile_name: str) -> ContainerStatus:
    """Остановить контейнер без удаления и без изменения mcp.json."""
    config = load_config(profile_name)
    if config.docker.compose_dir:
        compose_path = Path(config.docker.compose_dir).expanduser().resolve()
        if (compose_path / "docker-compose.yml").exists():
            compose_stop(compose_path, profile_name)
            return get_status(profile_name)

    client = _get_client()
    name = container_name(profile_name)
    try:
        container = client.containers.get(name)
        container.stop(timeout=10)
    except Exception as exc:
        return ContainerStatus(profile_name=profile_name, running=False, error=str(exc))
    return get_status(profile_name)


def remove_container(profile_name: str) -> None:
    from packages.kb.indexer.cursor_mcp_config import remove_profile_from_cursor_mcp

    config = load_config(profile_name)
    if config.docker.compose_dir:
        compose_path = Path(config.docker.compose_dir).expanduser().resolve()
        if (compose_path / "docker-compose.yml").exists():
            try:
                compose_down(compose_path, profile_name)
            except Exception:
                pass

    client = _get_client()
    name = container_name(profile_name)
    try:
        container = client.containers.get(name)
        container.remove(force=True)
    except Exception:
        pass

    try:
        remove_profile_from_cursor_mcp(config)
    except Exception as exc:
        logger.warning("Не удалось удалить MCP из mcp.json для %s: %s", profile_name, exc)


def docker_available() -> tuple[bool, str]:
    try:
        client = _get_client()
        client.ping()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def get_container_logs(profile_name: str, tail: int = 300) -> str:
    config = load_config(profile_name)
    if config.docker.compose_dir:
        compose_path = Path(config.docker.compose_dir).expanduser().resolve()
        if (compose_path / "docker-compose.yml").exists():
            return compose_logs(compose_path, profile_name, tail=tail)

    name = container_name(profile_name)
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(tail), name],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = (result.stdout or "") + (result.stderr or "")
        output = output.strip()
        if output:
            return output
        if result.returncode != 0:
            return f"docker logs завершился с кодом {result.returncode}"
        return "(контейнер пока не писал в stdout/stderr — это нормально для MCP-сервера в ожидании)"
    except Exception as exc:
        return f"Не удалось прочитать лог контейнера: {exc}"


def mcp_entry_for_profile(config: ProfileConfig, host_port: int | None = None) -> dict:
    port = host_port or config.mcp.port
    return {"url": mcp_url(port)}
