"""Checkpoint для возобновления прерванной полной индексации."""

from __future__ import annotations

import json
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.profiles import PROJECT_ROOT

CHECKPOINT_VERSION = 1


def checkpoint_path(config: ProfileConfig) -> Path:
    path = PROJECT_ROOT / "data" / "profiles" / config.profile_name / "index-checkpoint.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_checkpoint(config: ProfileConfig) -> dict | None:
    path = checkpoint_path(config)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if int(data.get("version", 0)) != CHECKPOINT_VERSION:
            return None
        return data
    except (OSError, json.JSONDecodeError):
        return None


def save_checkpoint(
    config: ProfileConfig,
    *,
    processed_paths: list[str],
    phase: str,
    full: bool,
) -> None:
    payload = {
        "version": CHECKPOINT_VERSION,
        "profile": config.profile_name,
        "full": full,
        "phase": phase,
        "processed": sorted(set(processed_paths)),
        "processed_count": len(set(processed_paths)),
    }
    checkpoint_path(config).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def clear_checkpoint(config: ProfileConfig) -> None:
    path = checkpoint_path(config)
    if path.exists():
        path.unlink()


def checkpoint_summary(config: ProfileConfig) -> dict | None:
    """Краткая информация о незавершённой полной индексации для API/UI."""
    data = load_checkpoint(config)
    if not data or not data.get("full"):
        return None
    processed = data.get("processed") or []
    return {
        "available": True,
        "full": True,
        "phase": data.get("phase") or "",
        "processed_count": int(data.get("processed_count") or len(processed)),
    }
