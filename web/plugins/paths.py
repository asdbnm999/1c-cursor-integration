"""Пути Cursor CLI и каталогов расширений (кроссплатформенно, ТЗ §9.4)."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from web.settings import load_cursor_settings


def default_extensions_dirs() -> list[Path]:
    """Кандидаты каталогов расширений по ОС (порядок приоритета)."""
    home = Path.home()
    system = platform.system()
    candidates: list[Path] = []

    if system == "Darwin":
        candidates.extend(
            [
                home / "Library" / "Application Support" / "Cursor" / "User" / "extensions",
                home / ".cursor" / "extensions",
            ]
        )
    elif system == "Windows":
        userprofile = os.environ.get("USERPROFILE", str(home))
        appdata = os.environ.get("APPDATA", "")
        candidates.extend(
            [
                Path(userprofile) / ".cursor" / "extensions",
            ]
        )
        if appdata:
            candidates.append(Path(appdata) / "Cursor" / "User" / "extensions")
    else:
        candidates.append(home / ".cursor" / "extensions")

    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.expanduser()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(resolved)
    return unique


def _cursor_cli_candidates() -> list[str]:
    """Кандидаты бинарника cursor (PATH + типичные пути установки)."""
    candidates: list[str] = []
    cli = shutil.which("cursor")
    if cli:
        candidates.append(cli)

    system = platform.system()
    home = Path.home()
    if system == "Darwin":
        candidates.extend(
            [
                "/Applications/Cursor.app/Contents/Resources/app/bin/cursor",
                str(home / "Applications" / "Cursor.app" / "Contents" / "Resources" / "app" / "bin" / "cursor"),
            ]
        )
    elif system == "Windows":
        localappdata = os.environ.get("LOCALAPPDATA", "")
        if localappdata:
            candidates.append(str(Path(localappdata) / "Programs" / "cursor" / "Cursor.exe"))
    else:
        candidates.extend(
            [
                "/usr/bin/cursor",
                str(home / ".local" / "bin" / "cursor"),
            ]
        )

    seen: set[str] = set()
    unique: list[str] = []
    for path in candidates:
        if path and path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


def find_cursor_cli() -> str | None:
    """Путь к cursor, если `cursor --version` успешен."""
    for cli in _cursor_cli_candidates():
        if not Path(cli).is_file():
            continue
        try:
            result = subprocess.run(
                [cli, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0:
            return cli
    return None


def resolve_extensions_dir() -> tuple[Path | None, str]:
    """
    Каталог расширений для установки/сканирования.
    Возвращает (path, source) где source: configured | detected | none.
    """
    cursor_settings = load_cursor_settings()
    configured = (cursor_settings.get("cursor_extensions_dir") or "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path, "configured"

    for candidate in default_extensions_dirs():
        if candidate.is_dir():
            return candidate, "detected"

    # Первый кандидат даже если не существует — для сообщения об ошибке
    defaults = default_extensions_dirs()
    if defaults:
        return defaults[0], "none"
    return None, "none"


def cursor_paths_info() -> dict:
    configured_raw = (load_cursor_settings().get("cursor_extensions_dir") or "").strip()
    resolved, source = resolve_extensions_dir()
    cli = find_cursor_cli()
    return {
        "cli_available": cli is not None,
        "cli_path": cli,
        "extensions_dir": str(resolved) if resolved else None,
        "extensions_dir_source": source,
        "extensions_dir_configured": configured_raw or None,
        "extensions_dir_exists": bool(resolved and resolved.is_dir()),
        "default_candidates": [str(p) for p in default_extensions_dirs()],
    }
