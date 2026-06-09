"""Корневые пути KB внутри monorepo 1c-cursor."""

from __future__ import annotations

from pathlib import Path


def _detect_project_root() -> Path:
    """Корень репозитория: pyproject.toml + (web/app.py или packages/kb для Docker MCP)."""
    import os

    env_root = (os.environ.get("PROJECT_ROOT") or os.environ.get("KB_PROJECT_ROOT") or "").strip()
    if env_root:
        return Path(env_root).expanduser().resolve()

    here = Path(__file__).resolve().parent
    for base in (here, *here.parents):
        if not (base / "pyproject.toml").is_file():
            continue
        if (base / "web" / "app.py").is_file():
            return base
        if (base / "packages" / "kb").is_dir():
            return base
    return here.parent.parent.parent


PROJECT_ROOT = _detect_project_root()
KB_PACKAGE_ROOT = Path(__file__).resolve().parent
DOCKER_DIR = KB_PACKAGE_ROOT / "docker"
PROFILES_DIR = PROJECT_ROOT / "profiles"
DATA_PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"
HF_CACHE_DIR = PROJECT_ROOT / "data" / "hf_cache"

# PyPI для docker build: основной индекс + запасное зеркало.
DEFAULT_PIP_INDEX_URL = "https://pypi.org/simple"
DEFAULT_PIP_EXTRA_INDEX_URL = "https://mirror.yandex.ru/mirrors/pypi/simple/"
DEFAULT_PIP_TRUSTED_HOST = "pypi.org files.pythonhosted.org mirror.yandex.ru"
