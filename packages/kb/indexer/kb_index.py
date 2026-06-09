"""Обогащённый индекс конфигурации: движения, обратные связи, BSL-анализ."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from packages.kb.indexer.bsl_analysis import analyze_bsl_module
from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.extract_metadata import extract_metadata
from packages.kb.indexer.models import FileKind, SourceFormat
from packages.kb.indexer.object_modules import list_object_modules
from packages.kb.indexer.scanner import scan_profile

logger = logging.getLogger(__name__)

INDEX_VERSION = 1


def kb_index_path(config: ProfileConfig) -> Path:
    return (
        config.project_root
        / "data"
        / "profiles"
        / config.profile_name
        / "indexes"
        / "kb"
        / "index.json"
    )


def _object_key(object_type: str, object_name: str) -> str:
    return f"{object_type}:{object_name}"


def _infer_movement_kind_from_name(document_name: str) -> str:
    if "Приход" in document_name:
        return "Приход"
    if "Расход" in document_name:
        return "Расход"
    return ""


def _parse_register_ref(ref: str) -> tuple[str, str]:
    if "." in ref:
        rtype, rname = ref.split(".", 1)
        return rtype, rname
    return "AccumulationRegister", ref


def _metadata_entry(obj) -> dict[str, Any]:
    return {
        "object_type": obj.object_type,
        "object_name": obj.name,
        "synonym": obj.synonym,
        "path": obj.path,
        "attributes": obj.attributes,
        "tabular_sections": obj.tabular_sections,
        "register_records": list(obj.register_records),
        "dimensions": obj.dimensions,
        "resources": obj.resources,
        "register_type": obj.register_type,
        "posting": obj.posting,
        "real_time_posting": obj.real_time_posting,
        "subsystems": list(obj.subsystems),
    }


def _merge_movements(
    metadata_records: list[str],
    bsl_movements: list[dict[str, Any]],
    register_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}

    for ref in metadata_records:
        rtype, rname = _parse_register_ref(ref)
        reg_meta = register_lookup.get(f"{rtype}:{rname}", {})
        merged[rname] = {
            "register_type": rtype,
            "register_name": rname,
            "register_synonym": reg_meta.get("synonym", ""),
            "movement_kind": "",
            "dimensions": [d["name"] for d in reg_meta.get("dimensions", [])],
            "resources": [r["name"] for r in reg_meta.get("resources", [])],
            "declared_in_metadata": True,
            "formed_in_code": False,
            "handler": "",
        }

    for mov in bsl_movements:
        rname = mov["register_name"]
        existing = merged.get(rname)
        if existing:
            if mov.get("movement_kind"):
                existing["movement_kind"] = mov["movement_kind"]
            existing["formed_in_code"] = True
            existing["handler"] = mov.get("handler", existing["handler"])
        else:
            rtype = mov.get("register_type", "AccumulationRegister")
            reg_meta = register_lookup.get(f"{rtype}:{rname}", {})
            merged[rname] = {
                "register_type": rtype,
                "register_name": rname,
                "register_synonym": reg_meta.get("synonym", ""),
                "movement_kind": mov.get("movement_kind", ""),
                "dimensions": [d["name"] for d in reg_meta.get("dimensions", [])],
                "resources": [r["name"] for r in reg_meta.get("resources", [])],
                "declared_in_metadata": False,
                "formed_in_code": True,
                "handler": mov.get("handler", ""),
            }

    return list(merged.values())


def build_kb_index(config: ProfileConfig) -> Path:
    path = kb_index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)

    objects: dict[str, dict[str, Any]] = {}
    register_to_documents: dict[str, list[dict[str, Any]]] = {}
    subsystem_objects: dict[str, list[str]] = {}

    metadata_by_key: dict[str, Any] = {}
    for entry in scan_profile(config):
        if entry.kind != FileKind.METADATA:
            continue
        if entry.source_format == SourceFormat.XML_EXPORT and "/Forms/" in entry.relative_path:
            continue
        try:
            obj = extract_metadata(entry.path, entry.source_name, entry.source_format)
        except Exception as exc:
            logger.warning("KB index skip metadata %s: %s", entry.path, exc)
            continue
        key = _object_key(obj.object_type, obj.name)
        metadata_by_key[key] = obj
        objects[key] = _metadata_entry(obj)
        for sub in obj.subsystems:
            subsystem_objects.setdefault(sub, []).append(f"{obj.object_type}.{obj.name}")

    register_lookup = {
        key: {
            "synonym": val.synonym,
            "dimensions": val.dimensions,
            "resources": val.resources,
            "register_type": val.register_type,
        }
        for key, val in metadata_by_key.items()
        if val.object_type in ("AccumulationRegister", "InformationRegister", "AccountingRegister")
    }

    for key, obj in metadata_by_key.items():
        if obj.object_type not in ("Document", "DataProcessor"):
            continue
        bsl_movements: list[dict[str, Any]] = []
        handlers: list[dict[str, Any]] = []
        modules: list[dict[str, str]] = []
        try:
            for mod in list_object_modules(config, obj.object_type, obj.name):
                modules.append({
                    "name": mod["name"],
                    "relative_path": mod["relative_path"],
                    "kind": mod["kind"],
                })
                analysis = analyze_bsl_module(mod["path"])
                bsl_movements.extend(analysis["movements"])
                handlers.extend(analysis["handlers"])
        except Exception as exc:
            logger.warning("KB index BSL skip %s: %s", key, exc)

        movements = _merge_movements(obj.register_records, bsl_movements, register_lookup)
        if any(h["name"] == "ОбработкаПроведения" for h in handlers):
            for mov in movements:
                if mov.get("formed_in_code"):
                    mov["handler"] = "ОбработкаПроведения"
        inferred_kind = _infer_movement_kind_from_name(obj.name)
        if inferred_kind:
            for mov in movements:
                if not mov.get("movement_kind"):
                    mov["movement_kind"] = inferred_kind
        objects[key]["movements"] = movements
        objects[key]["posting_handlers"] = handlers
        objects[key]["modules"] = modules

        for mov in movements:
            reg_key = f"{mov['register_type']}:{mov['register_name']}"
            register_to_documents.setdefault(reg_key, []).append({
                "document_type": obj.object_type,
                "document": obj.name,
                "movement_kind": mov.get("movement_kind", ""),
            })

    for sub_name, items in subsystem_objects.items():
        subsystem_objects[sub_name] = sorted(set(items))

    payload = {
        "version": INDEX_VERSION,
        "profile": config.profile_name,
        "objects": objects,
        "register_to_documents": register_to_documents,
        "subsystem_objects": subsystem_objects,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(
        "KB index: %d объектов, %d регистровых связей → %s",
        len(objects),
        len(register_to_documents),
        path,
    )
    return path


def load_kb_index(config: ProfileConfig) -> dict[str, Any]:
    path = kb_index_path(config)
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Не удалось прочитать KB index: %s", exc)
        return {}


def get_object_from_index(
    config: ProfileConfig,
    object_type: str,
    object_name: str,
) -> dict[str, Any] | None:
    index = load_kb_index(config)
    return (index.get("objects") or {}).get(_object_key(object_type, object_name))
