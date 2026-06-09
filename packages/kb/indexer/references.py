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


_QUERY_MARKERS = ("ВЫБРАТЬ", "ИЗ", "РегистрНакопления", "РегистрСведений", "Запрос.Текст")


def _file_type(path: str) -> str:
    if path.lower().endswith(".bsl"):
        return "bsl"
    if path.lower().endswith(".xml") or path.lower().endswith(".mdo"):
        return "xml"
    return "other"


def _context_kind(path: str, context: str) -> str:
    if any(marker in context for marker in _QUERY_MARKERS):
        return "query"
    if path.lower().endswith(".bsl"):
        return "module"
    if path.lower().endswith((".xml", ".mdo")):
        return "metadata"
    return "other"


def _apply_scope(refs: list[dict], scope: str) -> list[dict]:
    scope = (scope or "all").lower()
    if scope == "all":
        return refs
    if scope == "metadata":
        return [r for r in refs if r.get("file_type") == "xml"]
    if scope == "bsl":
        return [r for r in refs if r.get("file_type") == "bsl"]
    if scope == "queries":
        return [r for r in refs if r.get("context_kind") == "query"]
    return refs


def _enrich_ref(entry: dict) -> dict:
    path = entry.get("relative_path") or entry.get("path", "")
    context = entry.get("context", "")
    return {
        **entry,
        "file_type": _file_type(path),
        "context_kind": _context_kind(path, context),
    }


def find_references(
    config: ProfileConfig,
    identifier: str,
    *,
    limit: int = 50,
    object_type: str = "",
    scope: str = "all",
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
        refs = [_enrich_ref(r) for r in find_in_index(config, ident, limit=limit * 3, object_type=object_type)]
        return _apply_scope(refs, scope)[:limit]

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
            results.append(_enrich_ref({
                "path": entry.path,
                "relative_path": entry.relative_path,
                "line": line_no,
                "context": line_text[:200],
            }))
            if len(results) >= limit * 3:
                break
        if len(results) >= limit * 3:
            break
    return _apply_scope(results, scope)[:limit]
