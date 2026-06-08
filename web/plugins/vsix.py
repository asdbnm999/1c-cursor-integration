"""Чтение метаданных VSIX и обнаружение установленных расширений."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from web.plugins.constants import BUNDLED_VSIX_FILENAMES, VSIX_GLOB
from web.paths import EXTENSIONS_DIR


@dataclass(frozen=True)
class VsixMeta:
    path: Path
    filename: str
    publisher: str
    name: str
    version: str
    bundled: bool

    @property
    def extension_id(self) -> str:
        return f"{self.publisher}.{self.name}"

    @property
    def folder_name(self) -> str:
        return f"{self.extension_id}-{self.version}"


@dataclass(frozen=True)
class InstalledExtension:
    extension_id: str
    version: str
    path: Path


def read_vsix_meta(vsix_path: Path) -> VsixMeta:
    """Извлечь publisher, name, version из extension/package.json внутри VSIX."""
    vsix_path = vsix_path.resolve()
    with zipfile.ZipFile(vsix_path) as archive:
        try:
            raw = archive.read("extension/package.json")
        except KeyError as exc:
            raise ValueError(f"В VSIX нет extension/package.json: {vsix_path}") from exc
        data = json.loads(raw.decode("utf-8"))
    publisher = str(data.get("publisher") or "").strip()
    name = str(data.get("name") or "").strip()
    version = str(data.get("version") or "").strip()
    if not publisher or not name or not version:
        raise ValueError(f"Неполный package.json в {vsix_path.name}")
    return VsixMeta(
        path=vsix_path,
        filename=vsix_path.name,
        publisher=publisher,
        name=name,
        version=version,
        bundled=vsix_path.name in BUNDLED_VSIX_FILENAMES,
    )


def list_vsix_files(extensions_dir: Path | None = None) -> list[Path]:
    root = extensions_dir or EXTENSIONS_DIR
    if not root.is_dir():
        return []
    files = sorted(root.glob(VSIX_GLOB), key=lambda p: p.name.lower())
    return [p.resolve() for p in files if p.is_file()]


def scan_installed_extensions(extensions_dir: Path) -> dict[str, InstalledExtension]:
    """Найти установленные расширения по каталогам publisher.name-version."""
    result: dict[str, InstalledExtension] = {}
    if not extensions_dir.is_dir():
        return result
    pattern = re.compile(r"^(.+?)-(\d+(?:\.\d+)*)$")
    for entry in extensions_dir.iterdir():
        if not entry.is_dir():
            continue
        match = pattern.match(entry.name)
        if not match:
            continue
        extension_id, version = match.group(1), match.group(2)
        existing = result.get(extension_id)
        if existing is None or _version_key(version) > _version_key(existing.version):
            result[extension_id] = InstalledExtension(
                extension_id=extension_id,
                version=version,
                path=entry,
            )
    return result


def _version_key(version: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in version.split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def compare_versions(left: str, right: str) -> int:
    """-1 если left < right, 0 если равны, 1 если left > right."""
    lk, rk = _version_key(left), _version_key(right)
    if lk < rk:
        return -1
    if lk > rk:
        return 1
    return 0


def install_state(
    meta: VsixMeta,
    installed: dict[str, InstalledExtension],
) -> tuple[str, str, str | None]:
    """
    Возвращает (state, status_label, installed_version).
    state: not_installed | same_version | update_available | older_installed
    """
    current = installed.get(meta.extension_id)
    if current is None:
        return "not_installed", "Не установлено", None
    cmp = compare_versions(meta.version, current.version)
    if cmp == 0:
        return "same_version", f"v{current.version}", current.version
    if cmp > 0:
        return "update_available", "Доступно обновление", current.version
    return "older_installed", f"v{current.version}", current.version


def vsix_to_dict(
    meta: VsixMeta,
    installed: dict[str, InstalledExtension],
) -> dict[str, Any]:
    state, label, installed_version = install_state(meta, installed)
    current = installed.get(meta.extension_id)
    return {
        "path": str(meta.path),
        "filename": meta.filename,
        "bundled": meta.bundled,
        "publisher": meta.publisher,
        "name": meta.name,
        "version": meta.version,
        "extension_id": meta.extension_id,
        "install_state": state,
        "status_label": label,
        "installed_version": installed_version,
        "installed_path": str(current.path) if current else None,
    }
