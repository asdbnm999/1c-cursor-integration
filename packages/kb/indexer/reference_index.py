"""Индекс ссылок на идентификаторы в BSL — build-time."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.models import FileKind

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
_IDENTIFIER_RE = re.compile(
    r"(?<![\wА-Яа-яЁё])([\wА-Яа-яЁё][\wА-Яа-яЁё0-9]*)(?![\wА-Яа-яЁё])",
    re.UNICODE,
)


def reference_index_path(config: ProfileConfig) -> Path:
    return (
        config.project_root
        / "data"
        / "profiles"
        / config.profile_name
        / "indexes"
        / "references"
        / "index.json"
    )


def _scan_bsl_file(path: Path, relative_path: str) -> list[dict]:
    try:
        content = path.read_text(encoding="utf-8-sig", errors="replace")
    except OSError:
        return []
    entries: list[dict] = []
    for line_no, line in enumerate(content.splitlines(), start=1):
        for match in _IDENTIFIER_RE.finditer(line):
            ident = match.group(1)
            if len(ident) < 3:
                continue
            entries.append({
                "identifier": ident,
                "path": str(path),
                "relative_path": relative_path,
                "line": line_no,
                "context": line.strip()[:200],
            })
    return entries


def build_reference_index(config: ProfileConfig, bsl_entries: list) -> Path:
    """Строит индекс идентификаторов из BSL-файлов профиля."""
    from packages.kb.indexer.scanner import scan_profile

    path = reference_index_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)

    if bsl_entries is None:
        bsl_entries = [e for e in scan_profile(config) if e.kind == FileKind.BSL]

    all_entries: list[dict] = []
    for entry in bsl_entries:
        all_entries.extend(_scan_bsl_file(Path(entry.path), entry.relative_path))

    payload = {
        "version": INDEX_VERSION,
        "profile": config.profile_name,
        "entries": all_entries,
        "identifiers_count": len({e["identifier"] for e in all_entries}),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    logger.info(
        "Reference index: %d записей, %d идентификаторов → %s",
        len(all_entries),
        payload["identifiers_count"],
        path,
    )
    return path


def load_reference_index(config: ProfileConfig) -> dict[str, list[dict]]:
    path = reference_index_path(config)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Не удалось прочитать reference index: %s", exc)
        return {}

    by_id: dict[str, list[dict]] = {}
    for entry in data.get("entries") or []:
        ident = entry.get("identifier", "")
        if ident:
            by_id.setdefault(ident, []).append(entry)
    return by_id


def find_in_index(
    config: ProfileConfig,
    identifier: str,
    *,
    limit: int = 50,
    object_type: str = "",
) -> list[dict]:
    index = load_reference_index(config)
    hits = index.get(identifier.strip(), [])
    if object_type:
        hits = [h for h in hits if object_type in h.get("relative_path", "")]
    return hits[:limit]
