"""Загрузка и сохранение настроек приложения."""

from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

from web import paths
from web.paths import DEFAULT_DOCKER_ROOT


def _default_settings() -> dict[str, Any]:
    return {
        "ui": {
            "palette": "midnight",
        },
        "docker": {
            "root": str(DEFAULT_DOCKER_ROOT),
            "pip_index_url": "https://mirror.yandex.ru/mirrors/pypi/simple/",
            "pip_trusted_host": "mirror.yandex.ru",
        },
        "plugins": {
            "installed": [],
        },
        "mcp": {
            "standard": {
                "searxng": {"enabled": False},
                "1c-syntax-helper": {"enabled": False},
            },
            "kb_profiles": {},
        },
        "rules": {
            "last_output": {},
        },
        "sections": {
            "plugins": "not_started",
            "mcp": "not_started",
            "kb": "not_started",
            "rules": "not_started",
        },
    }


def _default_cursor_settings() -> dict[str, Any]:
    return {
        "cursor_extensions_dir": "",
        "mcp_config_path": "",
    }


def _ensure_data_dir() -> None:
    paths.DATA_DIR.mkdir(parents=True, exist_ok=True)


def _init_from_example(path: Path, example: Path, default: dict[str, Any]) -> dict[str, Any]:
    _ensure_data_dir()
    if path.exists():
        return load_json(path)
    if example.exists():
        shutil.copy(example, path)
        return load_json(path)
    save_json(path, default)
    return deepcopy(default)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path: Path, data: dict[str, Any]) -> None:
    _ensure_data_dir()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_settings() -> dict[str, Any]:
    return _init_from_example(
        paths.SETTINGS_PATH,
        paths.SETTINGS_EXAMPLE_PATH,
        _default_settings(),
    )


def save_settings(data: dict[str, Any]) -> None:
    save_json(paths.SETTINGS_PATH, data)


def load_cursor_settings() -> dict[str, Any]:
    return _init_from_example(
        paths.CURSOR_SETTINGS_PATH,
        paths.CURSOR_SETTINGS_EXAMPLE_PATH,
        _default_cursor_settings(),
    )


def save_cursor_settings(data: dict[str, Any]) -> None:
    save_json(paths.CURSOR_SETTINGS_PATH, data)


def get_palette() -> str:
    palette = load_settings().get("ui", {}).get("palette", "midnight")
    if palette not in {"midnight", "ocean", "forest", "ember"}:
        return "midnight"
    return palette


def export_settings() -> dict[str, Any]:
    """Экспорт настроек проекта (без chroma/KB indexes, ТЗ §5.4)."""
    return {
        "version": 1,
        "settings": load_settings(),
        "cursor": load_cursor_settings(),
    }


def import_settings(bundle: dict[str, Any]) -> None:
    """Импорт настроек из JSON."""
    if "settings" in bundle and isinstance(bundle["settings"], dict):
        save_settings(bundle["settings"])
    if "cursor" in bundle and isinstance(bundle["cursor"], dict):
        save_cursor_settings(bundle["cursor"])
