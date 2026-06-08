"""Снимок метаданных профиля для быстрого compare."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.extract_metadata import extract_metadata
from packages.kb.indexer.models import FileKind, SourceFormat
from packages.kb.indexer.scanner import scan_profile

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 1


def snapshot_path(config: ProfileConfig) -> Path:
    return config.project_root / "data" / "profiles" / config.profile_name / "metadata-snapshot.json"


def build_metadata_snapshot(config: ProfileConfig) -> Path:
    path = snapshot_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    objects: dict[str, dict] = {}

    for entry in scan_profile(config):
        if entry.kind != FileKind.METADATA:
            continue
        try:
            obj = extract_metadata(entry.path, entry.source_name, entry.source_format)
        except Exception as exc:
            logger.warning("Snapshot skip %s: %s", entry.path, exc)
            continue
        key = f"{obj.object_type}:{obj.name}"
        objects[key] = {
            "object_type": obj.object_type,
            "object_name": obj.name,
            "synonym": obj.synonym,
            "attributes_count": len(obj.attributes),
            "attributes": obj.attributes,
            "register_records": list(obj.register_records),
            "path": obj.path,
        }

    payload = {
        "version": SNAPSHOT_VERSION,
        "profile": config.profile_name,
        "format": config.format,
        "objects": objects,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Metadata snapshot: %d объектов → %s", len(objects), path)
    return path


def load_metadata_snapshot(profile_name: str, project_root: Path | None = None) -> dict:
    from packages.kb.indexer.config import load_config

    config = load_config(profile_name)
    path = snapshot_path(config)
    if not path.is_file():
        return {"objects": {}}
    return json.loads(path.read_text(encoding="utf-8"))
