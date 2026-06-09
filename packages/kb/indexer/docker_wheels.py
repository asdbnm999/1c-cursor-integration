"""Подготовка Linux wheels на хосте для офлайн-сборки KB Docker-образа."""

from __future__ import annotations

import hashlib
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from packages.kb.paths import KB_PACKAGE_ROOT, PROJECT_ROOT

WHEELS_DIR = KB_PACKAGE_ROOT / "docker" / "wheels-kb-mcp"
REQUIREMENTS_FILE = KB_PACKAGE_ROOT / "docker" / "requirements-kb-mcp.txt"
MARKER_FILE = WHEELS_DIR / ".wheels-complete"
PREFETCH_IMAGE = "python:3.12-slim"

# Минимальный набор нативных пакетов в кэше wheels (проверка полноты).
_REQUIRED_PACKAGES = (
    "chromadb",
    "onnxruntime",
    "numpy",
    "mcp",
    "sentence-transformers",
)


def _requirements_fingerprint() -> str:
    return hashlib.sha256(REQUIREMENTS_FILE.read_bytes()).hexdigest()[:16]


def resolve_docker_build_platform() -> str:
    """Docker platform для KB-образа (onnxruntime/chromadb — linux/amd64 wheels)."""
    return "linux/amd64"


def _pip_wheel_target() -> tuple[str, str, str]:
    """manylinux-тег (для тестов и fallback)."""
    return "manylinux_2_28_x86_64", "3.12", "cp312"


def _normalize_pkg_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def _installed_artifacts() -> set[str]:
    if not WHEELS_DIR.is_dir():
        return set()
    return {
        path.name
        for path in WHEELS_DIR.iterdir()
        if path.is_file() and path.name != ".wheels-complete"
    }


def _has_package(pkg_name: str, artifacts: set[str]) -> bool:
    prefix = _normalize_pkg_name(pkg_name) + "-"
    return any(_normalize_pkg_name(name).startswith(prefix) for name in artifacts)


def _missing_required(artifacts: set[str]) -> list[str]:
    return [pkg for pkg in _REQUIRED_PACKAGES if not _has_package(pkg, artifacts)]


def wheels_cache_ready(*, force: bool = False) -> bool:
    if force or not MARKER_FILE.exists() or not WHEELS_DIR.is_dir():
        return False
    try:
        marker = MARKER_FILE.read_text(encoding="utf-8").strip()
        if marker != _requirements_fingerprint():
            return False
    except OSError:
        return False
    artifacts = _installed_artifacts()
    if len(artifacts) < 40:
        return False
    return not _missing_required(artifacts)


def _clear_wheels_dir() -> None:
    WHEELS_DIR.mkdir(parents=True, exist_ok=True)
    for path in WHEELS_DIR.iterdir():
        if path.name != ".wheels-complete":
            path.unlink()


def _download_wheels_via_docker(log: Callable[[str], None]) -> None:
    """Скачать wheels внутри официального python:3.12-slim (корректное дерево deps)."""
    docker_plat = resolve_docker_build_platform()
    req_host = REQUIREMENTS_FILE.resolve()
    wheels_host = WHEELS_DIR.resolve()

    inner = (
        "pip install --no-cache-dir -q pip && "
        "pip download -r /req.txt -d /wheels --prefer-binary"
    )
    cmd = [
        "docker",
        "run",
        "--rm",
        "--platform",
        docker_plat,
        "-v",
        f"{req_host}:/req.txt:ro",
        "-v",
        f"{wheels_host}:/wheels",
        PREFETCH_IMAGE,
        "bash",
        "-lc",
        inner,
    ]
    log(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.stdout:
        for line in proc.stdout.splitlines()[-40:]:
            log(line)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        if err:
            for line in err.splitlines()[-20:]:
                log(line)
        raise RuntimeError(
            "Не удалось скачать wheels через Docker (python:3.12-slim). "
            "Проверьте, что Docker daemon запущен и есть доступ в интернет."
        )


def _download_wheels_host_fallback(log: Callable[[str], None]) -> None:
    """Запасной путь без docker run (только если prefetch-контейнер недоступен)."""
    plat, py_ver, abi = _pip_wheel_target()
    cmd = [
        sys.executable,
        "-m",
        "pip",
        "download",
        "-r",
        str(REQUIREMENTS_FILE),
        "-d",
        str(WHEELS_DIR),
        "--prefer-binary",
        "--only-binary",
        ":all:",
        "--platform",
        plat,
        "--python-version",
        py_ver,
        "--implementation",
        "cp",
        "--abi",
        abi,
    ]
    log(f"$ {' '.join(cmd)} (fallback)")
    proc = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
    if proc.stdout:
        for line in proc.stdout.splitlines():
            log(line)
    if proc.returncode != 0:
        err = (proc.stderr or "").strip()
        if err:
            log(err)
        raise RuntimeError("Fallback pip download не удался.")


def ensure_kb_mcp_wheels(
    *,
    force: bool = False,
    log: Callable[[str], None] | None = None,
) -> Path:
    """Скачать зависимости KB MCP для офлайн docker build."""
    emit = log or (lambda _line: None)
    if not REQUIREMENTS_FILE.is_file():
        raise FileNotFoundError(f"Не найден {REQUIREMENTS_FILE}")

    if wheels_cache_ready(force=force):
        emit("✓ Wheels KB MCP готовы — Docker соберётся без PyPI в контейнере")
        return WHEELS_DIR

    docker_plat = resolve_docker_build_platform()
    emit(
        f"→ Скачивание wheels через Docker ({PREFETCH_IMAGE}, {docker_plat})… "
        "Первый раз: 5–20 мин (зависимости ML могут быть крупными)."
    )
    if platform.machine().lower() in {"arm64", "aarch64"}:
        emit("ℹ На Apple Silicon wheels и образ KB — linux/amd64.")

    _clear_wheels_dir()

    try:
        _download_wheels_via_docker(emit)
    except RuntimeError as exc:
        emit(f"WARN: {exc}")
        emit("→ Повтор через host pip download (ограниченный fallback)…")
        _clear_wheels_dir()
        _download_wheels_host_fallback(emit)

    present = _installed_artifacts()
    missing = _missing_required(present)
    if missing:
        raise RuntimeError(
            "Не хватает пакетов в wheels: "
            + ", ".join(missing)
            + ". Повторите с «Пересобрать образ»."
        )

    count = len(present)
    if count < 40:
        raise RuntimeError(f"Слишком мало wheels ({count}). Повторите сборку.")

    MARKER_FILE.write_text(_requirements_fingerprint() + "\n", encoding="utf-8")
    emit(f"✓ Скачано файлов: {count}")
    return WHEELS_DIR
