"""Docker deploy/stop/logs для §2 (код; запуск — по действию пользователя в UI)."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]

import httpx

from web.docker_naming import mcp_stack_name
from web.mcp.constants import SEARXNG_SLUG, SYNTAX_REPO_DIRNAME, SYNTAX_REPO_URL, SYNTAX_SLUG
from web.mcp.syntax_patch import apply_mcp_patch

COMPOSE_TIMEOUT = 600
HEALTH_TIMEOUT_SEC = 300
INDEX_TIMEOUT_SEC = 900


def _run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int = COMPOSE_TIMEOUT,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def docker_available() -> tuple[bool, str]:
    if not _run(["docker", "version"], timeout=15).returncode == 0:
        return False, "Docker CLI недоступен"
    info = _run(["docker", "info"], timeout=20)
    if info.returncode != 0:
        return False, (info.stderr or info.stdout or "Docker daemon недоступен").strip().splitlines()[0]
    return True, "ok"


def clone_syntax_repo(target_dir: Path) -> dict[str, Any]:
    repo = target_dir / SYNTAX_REPO_DIRNAME
    if (repo / ".git").is_dir():
        return {"status": "exists", "path": str(repo)}
    target_dir.mkdir(parents=True, exist_ok=True)
    proc = _run(
        ["git", "clone", "--depth", "1", SYNTAX_REPO_URL, str(repo)],
        timeout=300,
    )
    if proc.returncode != 0:
        return {
            "status": "error",
            "path": str(repo),
            "message": (proc.stderr or proc.stdout or "git clone failed").strip(),
        }
    return {"status": "cloned", "path": str(repo)}


def compose_pull(compose_dir: Path) -> dict[str, Any]:
    proc = _run(["docker", "compose", "pull"], cwd=compose_dir)
    return _compose_result(proc, action="pull")


def compose_build(compose_dir: Path, service: str | None = None) -> dict[str, Any]:
    args = ["docker", "compose", "build"]
    if service:
        args.append(service)
    proc = _run(args, cwd=compose_dir, timeout=900)
    return _compose_result(proc, action="build")


def compose_up(compose_dir: Path) -> dict[str, Any]:
    proc = _run(["docker", "compose", "up", "-d"], cwd=compose_dir)
    return _compose_result(proc, action="up")


def compose_down(compose_dir: Path) -> dict[str, Any]:
    proc = _run(["docker", "compose", "down"], cwd=compose_dir)
    return _compose_result(proc, action="down")


def compose_logs(compose_dir: Path, *, tail: int = 100) -> str:
    proc = _run(
        ["docker", "compose", "logs", "--tail", str(tail), "--no-color"],
        cwd=compose_dir,
        timeout=60,
    )
    return (proc.stdout or "") + (proc.stderr or "")


def _compose_result(proc: subprocess.CompletedProcess[str], *, action: str) -> dict[str, Any]:
    ok = proc.returncode == 0
    return {
        "ok": ok,
        "action": action,
        "returncode": proc.returncode,
        "stdout": (proc.stdout or "")[-4000:],
        "stderr": (proc.stderr or "")[-4000:],
        "message": "OK" if ok else (proc.stderr or proc.stdout or f"docker compose {action} failed").strip()[:500],
    }


def published_host_port(container_name: str) -> int | None:
    """Host-порт MCP-контейнера из `docker port` (первый опубликованный TCP)."""
    proc = _run(["docker", "port", container_name], timeout=15)
    if proc.returncode != 0:
        return None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        if "->" not in line:
            continue
        host_part = line.split("->", 1)[1].strip()
        if ":" not in host_part:
            continue
        try:
            return int(host_part.rsplit(":", 1)[-1])
        except ValueError:
            continue
    return None


def container_status(container_name: str) -> dict[str, Any]:
    proc = _run(
        [
            "docker",
            "inspect",
            container_name,
            "--format",
            "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
        ],
        timeout=15,
    )
    if proc.returncode != 0:
        return {"name": container_name, "running": False, "health": "missing", "detail": "контейнер не найден"}
    parts = (proc.stdout or "").strip().split("|", 1)
    state = parts[0] if parts else "unknown"
    health = parts[1] if len(parts) > 1 else "none"
    return {
        "name": container_name,
        "running": state == "running",
        "state": state,
        "health": health,
        "detail": f"{state}/{health}",
    }


def wait_http_health(
    url: str,
    *,
    timeout_sec: int = HEALTH_TIMEOUT_SEC,
    on_tick: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    started = time.time()
    deadline = started + timeout_sec
    last_error = ""
    while time.time() < deadline:
        if on_tick:
            on_tick(int(time.time() - started), timeout_sec)
        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(url)
            if resp.status_code < 400:
                return {"ok": True, "url": url, "status_code": resp.status_code}
            last_error = f"HTTP {resp.status_code}"
        except httpx.HTTPError as exc:
            last_error = str(exc)
        time.sleep(3)
    return {"ok": False, "url": url, "error": last_error or "timeout"}


def mcp_ping(url: str) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        data = resp.json()
        if resp.status_code < 400 and data.get("result") == {}:
            return {"ok": True, "detail": "ping OK"}
        return {"ok": False, "detail": f"unexpected response: {resp.text[:200]}"}
    except (httpx.HTTPError, json.JSONDecodeError) as exc:
        return {"ok": False, "detail": str(exc)}


def mcp_cancelled(url: str) -> dict[str, Any]:
    payload = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": 1}}
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload, headers={"Content-Type": "application/json"})
        if resp.status_code < 400:
            return {"ok": True, "detail": "notifications/cancelled OK"}
        return {"ok": False, "detail": f"HTTP {resp.status_code}"}
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": str(exc)}


def syntax_indexing_state(payload: dict[str, Any]) -> str:
    indexing = payload.get("indexing") if isinstance(payload.get("indexing"), dict) else {}
    return (indexing.get("status") or payload.get("status") or payload.get("state") or "").lower()


def syntax_index_ready(payload: dict[str, Any]) -> bool:
    """Готовность индекса Syntax MCP по /index/status (1c-syntax-helper-mcp)."""
    state = syntax_indexing_state(payload)
    if state == "failed":
        return False
    if state in ("completed", "ready", "done"):
        return True
    docs = int(payload.get("documents_count") or 0)
    if state == "idle" and docs > 0:
        return True
    if payload.get("index_exists") and docs > 0 and state in ("idle", ""):
        return True
    return False


def syntax_index_error(payload: dict[str, Any]) -> str | None:
    state = syntax_indexing_state(payload)
    if state != "failed":
        return None
    indexing = payload.get("indexing") if isinstance(payload.get("indexing"), dict) else {}
    return (indexing.get("error_message") or "index failed").strip() or "index failed"


def wait_syntax_index(
    base_url: str,
    *,
    timeout_sec: int = INDEX_TIMEOUT_SEC,
    on_tick: Callable[[int, int], None] | None = None,
) -> dict[str, Any]:
    """Ждёт /index/status: completed или idle с документами в ES (ТЗ §10.5)."""
    status_url = base_url.replace("/mcp", "").rstrip("/") + "/index/status"
    started = time.time()
    deadline = started + timeout_sec
    last: dict[str, Any] = {}
    while time.time() < deadline:
        if on_tick:
            on_tick(int(time.time() - started), timeout_sec)
        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.get(status_url)
            if resp.status_code < 400:
                last = resp.json()
                err = syntax_index_error(last)
                if err:
                    return {"ok": False, "status": last, "error": err}
                if syntax_index_ready(last):
                    return {"ok": True, "status": last}
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
        time.sleep(5)
    return {"ok": False, "status": last, "error": "timeout waiting index"}


def deploy_server(
    server: str,
    compose_dir: Path,
    *,
    slug: str,
    mcp_port: int,
    skip_build: bool = False,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Полный deploy pipeline для выбранного сервера."""

    def emit(step: str, phase: str, extra: dict[str, Any] | None = None) -> None:
        if on_progress:
            on_progress(step, phase, extra)

    ok, msg = docker_available()
    if not ok:
        emit("prepare", "fail", {"message": msg})
        return {"ok": False, "stage": "docker", "message": msg}

    compose_dir = compose_dir.expanduser().resolve()
    if not (compose_dir / "docker-compose.yml").is_file():
        emit("prepare", "fail", {"message": "docker-compose.yml не найден"})
        return {"ok": False, "stage": "compose", "message": "docker-compose.yml не найден — сначала сгенерируйте"}

    steps: list[dict[str, Any]] = []
    mcp_svc = mcp_stack_name(slug)

    if server == SYNTAX_SLUG:
        emit("clone", "start")
        clone = clone_syntax_repo(compose_dir)
        steps.append({"step": "clone", **clone})
        if clone.get("status") == "error":
            emit("clone", "fail", clone)
            return {"ok": False, "stage": "clone", "steps": steps, "message": clone.get("message")}
        emit("clone", "done", clone)

        emit("patch", "start")
        repo = Path(clone["path"])
        patch = apply_mcp_patch(repo)
        steps.append({"step": "patch", **patch})
        if patch.get("status") == "error":
            emit("patch", "fail", patch)
            return {"ok": False, "stage": "patch", "steps": steps, "message": patch.get("message")}
        emit("patch", "done", patch)

        if not skip_build:
            emit("build", "start")
            build = compose_build(compose_dir, mcp_svc)
            steps.append({"step": "build", **build})
            if not build["ok"]:
                emit("build", "fail", build)
                return {"ok": False, "stage": "build", "steps": steps, "message": build.get("message")}
            emit("build", "done", build)
    else:
        emit("pull", "start")
        pull = compose_pull(compose_dir)
        steps.append({"step": "pull", **pull})
        if not pull["ok"]:
            emit("pull", "fail", pull)
            return {"ok": False, "stage": "pull", "steps": steps, "message": pull.get("message")}
        emit("pull", "done", pull)

    emit("up", "start")
    up = compose_up(compose_dir)
    steps.append({"step": "up", **up})
    if not up["ok"]:
        emit("up", "fail", up)
        return {"ok": False, "stage": "up", "steps": steps, "message": up.get("message")}
    emit("up", "done", up)

    mcp_url = f"http://127.0.0.1:{mcp_port}/mcp"
    health_base = f"http://127.0.0.1:{mcp_port}/health"

    def health_tick(elapsed: int, timeout: int) -> None:
        emit("health", "running", {"elapsed": elapsed, "timeout": timeout})

    emit("health", "start")
    health = wait_http_health(health_base, timeout_sec=HEALTH_TIMEOUT_SEC, on_tick=health_tick)
    steps.append({"step": "health", **health})
    emit("health", "done" if health.get("ok") else "fail", health)

    post: dict[str, Any] = {}
    if server == SYNTAX_SLUG:
        emit("mcp_protocol", "start")

        def index_tick(elapsed: int, timeout: int) -> None:
            emit("mcp_protocol", "running", {"elapsed": elapsed, "timeout": timeout})

        post["ping"] = mcp_ping(mcp_url)
        post["cancelled"] = mcp_cancelled(mcp_url)
        post["index"] = wait_syntax_index(mcp_url, on_tick=index_tick)
        steps.append({"step": "mcp_protocol", **post})
        protocol_ok = (
            post.get("ping", {}).get("ok")
            and post.get("cancelled", {}).get("ok")
            and post.get("index", {}).get("ok")
        )
        emit("mcp_protocol", "done" if protocol_ok else "fail", post)

    emit("container", "start")
    container = container_status(mcp_svc)
    steps.append({"step": "container", **container})
    emit("container", "done" if container.get("running") else "fail", container)

    if server != SYNTAX_SLUG:
        protocol_ok = True
    all_ok = health.get("ok") and container.get("running") and protocol_ok
    if all_ok:
        message = "Deploy завершён"
    elif server == SYNTAX_SLUG and not post.get("index", {}).get("ok") and container.get("running"):
        message = "Контейнер запущен, индексация HBK не завершена — см. шаги"
    else:
        message = "Deploy выполнен с предупреждениями — см. steps"
    return {
        "ok": all_ok,
        "stage": "done" if all_ok else "health_gate",
        "steps": steps,
        "mcp_url": mcp_url,
        "message": message,
    }


def find_orphaned_searxng() -> list[dict[str, str]]:
    proc = _run(
        [
            "docker",
            "ps",
            "-a",
            "--filter",
            "ancestor=isokoliuk/mcp-searxng:latest",
            "--format",
            "{{.Names}}|{{.Status}}|{{.Ports}}",
        ],
        timeout=30,
    )
    rows = []
    for line in (proc.stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) < 2:
            continue
        name, status = parts[0], parts[1]
        ports = parts[2] if len(parts) > 2 else ""
        if not re.search(r"0\.0\.0\.0:\d+->", ports) and "127.0.0.1" not in ports:
            rows.append({"name": name, "status": status, "ports": ports, "orphan": True})
    return rows
