"""Корневые пути KB внутри monorepo 1c-cursor."""

from __future__ import annotations

from pathlib import Path

# packages/kb/paths.py → parent.parent.parent = корень 1c-cursor
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
KB_PACKAGE_ROOT = Path(__file__).resolve().parent
DOCKER_DIR = KB_PACKAGE_ROOT / "docker"
PROFILES_DIR = PROJECT_ROOT / "profiles"
DATA_PROFILES_DIR = PROJECT_ROOT / "data" / "profiles"
HF_CACHE_DIR = PROJECT_ROOT / "data" / "hf_cache"
