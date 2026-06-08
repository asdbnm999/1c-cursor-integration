"""Сравнение двух профилей (ветки/релизы конфигурации)."""

from __future__ import annotations

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import CompareError, ProfileNotFoundError
from packages.kb.indexer.extract_metadata import extract_metadata
from packages.kb.indexer.bsl_compare import compare_bsl_modules
from packages.kb.indexer.metadata_snapshot import load_metadata_snapshot, snapshot_path
from packages.kb.indexer.models import FileKind
from packages.kb.indexer.profiles import profile_config_path
from packages.kb.indexer.scanner import scan_profile


def _metadata_map(profile_name: str) -> dict[str, dict]:
    if not profile_config_path(profile_name).exists():
        raise ProfileNotFoundError(f"Профиль не найден: {profile_name}")

    config = load_config(profile_name)
    if snapshot_path(config).is_file():
        snap = load_metadata_snapshot(profile_name)
        objects = snap.get("objects") or {}
        return {
            key: {
                "object_type": obj.get("object_type"),
                "name": obj.get("object_name"),
                "synonym": obj.get("synonym", ""),
                "path": obj.get("path", ""),
                "attributes_count": obj.get("attributes_count", 0),
                "attributes": obj.get("attributes", []),
                "register_records": list(obj.get("register_records") or []),
            }
            for key, obj in objects.items()
        }

    try:
        entries = scan_profile(config)
    except FileNotFoundError as exc:
        raise CompareError("Источник недоступен", details=str(exc)) from exc

    result: dict[str, dict] = {}
    for entry in entries:
        if entry.kind != FileKind.METADATA:
            continue
        try:
            obj = extract_metadata(entry.path, entry.source_name, entry.source_format)
            key = f"{obj.object_type}.{obj.name}"
            result[key] = {
                "object_type": obj.object_type,
                "name": obj.name,
                "synonym": obj.synonym,
                "path": obj.path,
                "attributes_count": len(obj.attributes),
                "register_records": list(obj.register_records),
            }
        except Exception:
            continue
    return result


def compare_profiles(profile_a: str, profile_b: str, *, include_bsl: bool = True) -> dict:
    """Сравнивает метаданные двух профилей."""
    if profile_a == profile_b:
        raise CompareError("Укажите два разных профиля")

    map_a = _metadata_map(profile_a)
    map_b = _metadata_map(profile_b)

    keys_a = set(map_a)
    keys_b = set(map_b)
    only_a = sorted(keys_a - keys_b)
    only_b = sorted(keys_b - keys_a)
    common = sorted(keys_a & keys_b)

    changed: list[dict] = []
    for key in common:
        a, b = map_a[key], map_b[key]
        diffs: list[str] = []
        if a.get("synonym") != b.get("synonym"):
            diffs.append("synonym")
        if a.get("attributes_count") != b.get("attributes_count"):
            diffs.append("attributes_count")
        if a.get("attributes") != b.get("attributes"):
            diffs.append("attributes")
        if a.get("register_records") != b.get("register_records"):
            diffs.append("register_records")
        if diffs:
            changed.append({
                "key": key,
                "diff_fields": diffs,
                "a": a,
                "b": b,
            })

    result = {
        "profile_a": profile_a,
        "profile_b": profile_b,
        "only_in_a": only_a,
        "only_in_b": only_b,
        "changed": changed,
        "summary": {
            "objects_a": len(map_a),
            "objects_b": len(map_b),
            "only_a_count": len(only_a),
            "only_b_count": len(only_b),
            "changed_count": len(changed),
        },
    }
    if include_bsl:
        bsl = compare_bsl_modules(profile_a, profile_b)
        result["bsl"] = bsl
        result["summary"]["bsl_changed_count"] = bsl["summary"]["changed_count"]
    return result
