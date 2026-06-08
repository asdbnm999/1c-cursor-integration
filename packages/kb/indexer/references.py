"""Поиск ссылок на идентификаторы в BSL-модулях."""

from __future__ import annotations

import re
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.exceptions import SourceNotFoundError
from packages.kb.indexer.models import FileKind
from packages.kb.indexer.reference_index import find_in_index, load_reference_index
from packages.kb.indexer.scanner import scan_profile

_REF_RE_CACHE: dict[str, re.Pattern] = {}


def _ref_pattern(identifier: str) -> re.Pattern:
    if identifier not in _REF_RE_CACHE:
        _REF_RE_CACHE[identifier] = re.compile(
            rf"(?<![\wА-Яа-яЁё]){re.escape(identifier)}(?![\wА-Яа-яЁё])",
            re.UNICODE,
        )
    return _REF_RE_CACHE[identifier]


def find_references(
    config: ProfileConfig,
    identifier: str,
    *,
    limit: int = 50,
    object_type: str = "",
) -> list[dict]:
    """Находит упоминания идентификатора в BSL-модулях проекта."""
    if not identifier.strip():
        return []

    base = config.source_base
    if not base.exists():
        raise SourceNotFoundError(
            "Каталог проекта недоступен",
            details=str(base),
        )

    ident = identifier.strip()
    indexed = load_reference_index(config)
    if indexed:
        return find_in_index(config, ident, limit=limit, object_type=object_type)

    pattern = _ref_pattern(ident)
    results: list[dict] = []

    try:
        entries = scan_profile(config)
    except FileNotFoundError as exc:
        raise SourceNotFoundError("Каталог проекта недоступен", details=str(exc)) from exc

    for entry in entries:
        if entry.kind != FileKind.BSL:
            continue
        if object_type and object_type not in entry.relative_path:
            continue
        try:
            content = Path(entry.path).read_text(encoding="utf-8-sig", errors="replace")
        except OSError:
            continue
        for match in pattern.finditer(content):
            line_no = content[: match.start()].count("\n") + 1
            line_text = content.splitlines()[line_no - 1].strip() if line_no else ""
            results.append({
                "path": entry.path,
                "relative_path": entry.relative_path,
                "line": line_no,
                "context": line_text[:200],
            })
            if len(results) >= limit:
                return results
    return results
