"""Список BSL-модулей объекта метаданных."""

from __future__ import annotations

from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.constants import BSL_MODULE_NAMES, FOLDER_TO_OBJECT_TYPE
from packages.kb.indexer.exceptions import SourceNotFoundError


def _object_dir(config: ProfileConfig, object_type: str, object_name: str) -> Path | None:
    base = config.source_base
    if not base.exists():
        raise SourceNotFoundError("Каталог проекта недоступен", details=str(base))

    if config.format == "edt":
        folder = None
        for f, t in FOLDER_TO_OBJECT_TYPE.items():
            if t == object_type:
                folder = f
                break
        if not folder:
            folder = object_type + "s" if not object_type.endswith("s") else object_type
        candidate = base / folder / object_name
        if candidate.is_dir():
            return candidate
        return None

    folder = None
    for f, t in FOLDER_TO_OBJECT_TYPE.items():
        if t == object_type:
            folder = f
            break
    if not folder:
        return None
    candidate = base / folder / object_name
    return candidate if candidate.is_dir() else None


def list_object_modules(
    config: ProfileConfig,
    object_type: str,
    object_name: str,
) -> list[dict]:
    """Возвращает BSL-модули объекта (ObjectModule, ManagerModule и т.д.)."""
    obj_dir = _object_dir(config, object_type, object_name)
    if obj_dir is None:
        return []

    modules: list[dict] = []
    if config.format == "edt":
        for bsl in obj_dir.rglob("*.bsl"):
            if bsl.name in BSL_MODULE_NAMES or bsl.name.endswith(".bsl"):
                rel = bsl.relative_to(config.source_base)
                modules.append({
                    "name": bsl.name,
                    "path": str(bsl),
                    "relative_path": rel.as_posix(),
                    "kind": bsl.stem.replace("Module", "") or "Module",
                })
    else:
        ext_dir = obj_dir / "Ext"
        if ext_dir.is_dir():
            for bsl in ext_dir.glob("*.bsl"):
                rel = bsl.relative_to(config.source_base)
                modules.append({
                    "name": bsl.name,
                    "path": str(bsl),
                    "relative_path": rel.as_posix(),
                    "kind": bsl.stem.replace("Module", "") or "Module",
                })
        forms_dir = obj_dir / "Forms"
        if forms_dir.is_dir():
            for bsl in forms_dir.rglob("*.bsl"):
                rel = bsl.relative_to(config.source_base)
                modules.append({
                    "name": bsl.name,
                    "path": str(bsl),
                    "relative_path": rel.as_posix(),
                    "kind": "FormModule",
                })

    return sorted(modules, key=lambda m: m["relative_path"])
