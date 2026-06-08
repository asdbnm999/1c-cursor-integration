"""Статус раздела плагинов и агрегация данных для API/UI."""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from web.paths import EXTENSIONS_DIR
from web.plugins.constants import BUNDLED_VSIX_FILENAMES
from web.plugins.paths import cursor_paths_info, resolve_extensions_dir
from web.plugins.vsix import (
    VsixMeta,
    list_vsix_files,
    read_vsix_meta,
    scan_installed_extensions,
    vsix_to_dict,
)
from web.settings import load_settings, save_settings


def compute_section_status(installed_map: dict, bundled_metas: list[VsixMeta]) -> str:
    """
    §6.4 / §9.6: ready = оба bundled установлены (версия >= bundled).
    in_progress = частично или устаревшая версия; not_started = ни одного bundled.
    """
    if not bundled_metas:
        return "not_started"

    from web.plugins.vsix import compare_versions

    installed_count = 0
    fully_ok = 0
    for meta in bundled_metas:
        current = installed_map.get(meta.extension_id)
        if current is None:
            continue
        installed_count += 1
        if compare_versions(current.version, meta.version) >= 0:
            fully_ok += 1

    if fully_ok == len(bundled_metas):
        return "ready"
    if installed_count > 0:
        return "in_progress"
    return "not_started"


def _merge_installed_records(new_entries: list[dict]) -> None:
    settings = load_settings()
    plugins = settings.setdefault("plugins", {})
    existing: list[dict] = list(plugins.get("installed") or [])
    by_id = {row.get("extension_id"): row for row in existing if row.get("extension_id")}
    for row in new_entries:
        ext_id = row.get("extension_id")
        if ext_id:
            by_id[ext_id] = row
    plugins["installed"] = list(by_id.values())
    save_settings(settings)


def update_section_status_in_settings() -> str:
    status_payload = get_plugins_status()
    status = status_payload["section_status"]
    settings = load_settings()
    settings.setdefault("sections", {})["plugins"] = status
    save_settings(settings)
    return status


def get_plugins_status() -> dict[str, Any]:
    extensions_dir, _ = resolve_extensions_dir()
    installed = scan_installed_extensions(extensions_dir) if extensions_dir else {}

    all_files = list_vsix_files()
    metas: list[VsixMeta] = []
    errors: list[str] = []
    for path in all_files:
        try:
            metas.append(read_vsix_meta(path))
        except ValueError as exc:
            errors.append(str(exc))

    bundled_metas = [m for m in metas if m.bundled]
    # гарантировать оба bundled в списке даже если файла нет
    present_names = {m.filename for m in bundled_metas}
    for name in BUNDLED_VSIX_FILENAMES:
        if name not in present_names:
            missing = EXTENSIONS_DIR / name
            errors.append(f"Bundled VSIX отсутствует: {missing}")

    additional_metas = [m for m in metas if not m.bundled]
    installed_dict = {k: v for k, v in installed.items()}

    section_status = compute_section_status(installed_dict, bundled_metas)

    update_available = any(
        item["install_state"] == "update_available"
        for item in (
            [vsix_to_dict(m, installed_dict) for m in bundled_metas]
        )
    )

    payload = {
        "bundled": [vsix_to_dict(m, installed_dict) for m in bundled_metas],
        "additional": [vsix_to_dict(m, installed_dict) for m in additional_metas],
        "cursor": cursor_paths_info(),
        "section_status": section_status,
        "update_banner": update_available,
        "update_banner_text": (
            "Доступно обновление bundled VSIX. Положите актуальный `.vsix` в `assets/extensions/` "
            "и переустановите."
            if update_available
            else None
        ),
        "errors": errors,
        "scanned_at": datetime.now(UTC).isoformat(),
    }
    settings = load_settings()
    if settings.get("sections", {}).get("plugins") != section_status:
        settings.setdefault("sections", {})["plugins"] = section_status
        save_settings(settings)
    return payload


def add_vsix_from_picker(source_path: str) -> dict[str, Any]:
    """Скопировать выбранный VSIX в assets/extensions/."""
    src = Path(source_path).expanduser().resolve()
    if not src.is_file():
        return {"ok": False, "error": "Файл не найден"}
    if src.suffix.lower() != ".vsix":
        return {"ok": False, "error": "Ожидается файл .vsix"}

    EXTENSIONS_DIR.mkdir(parents=True, exist_ok=True)
    dest = EXTENSIONS_DIR / src.name
    if dest.resolve() == src:
        return {"ok": True, "path": str(dest), "copied": False}

    shutil.copy2(src, dest)
    return {"ok": True, "path": str(dest.resolve()), "copied": True}


def save_cursor_extensions_dir(path: str) -> dict[str, Any]:
    from web.settings import load_cursor_settings, save_cursor_settings

    cleaned = path.strip()
    if not cleaned:
        return {"ok": False, "error": "Путь не может быть пустым"}
    expanded = Path(cleaned).expanduser()
    cursor = load_cursor_settings()
    cursor["cursor_extensions_dir"] = str(expanded)
    save_cursor_settings(cursor)
    return {
        "ok": True,
        "path": str(expanded),
        "exists": expanded.is_dir(),
    }


def apply_install_results(results: list[Any]) -> dict[str, Any]:
    from web.plugins.installer import InstallResult, record_installed_entries

    install_results = [r for r in results if isinstance(r, InstallResult)]
    entries = record_installed_entries(install_results)
    if entries:
        _merge_installed_records(entries)
    status = update_section_status_in_settings()
    return {"section_status": status}
