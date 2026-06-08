"""Сравнение BSL-модулей между профилями."""

from __future__ import annotations

import difflib
from pathlib import Path

from packages.kb.indexer.config import load_config
from packages.kb.indexer.models import FileKind
from packages.kb.indexer.scanner import scan_profile


def _bsl_relative_map(profile_name: str) -> dict[str, str]:
    config = load_config(profile_name)
    result: dict[str, str] = {}
    for entry in scan_profile(config):
        if entry.kind != FileKind.BSL:
            continue
        path = Path(entry.path)
        try:
            rel = path.relative_to(config.source_base).as_posix()
        except ValueError:
            rel = path.name
        try:
            result[rel] = path.read_text(encoding="utf-8")
        except OSError:
            continue
    return result


def compare_bsl_modules(
    profile_a: str,
    profile_b: str,
    *,
    limit: int = 50,
    preview_lines: int = 12,
) -> dict:
    """Сравнивает BSL-файлы двух профилей по относительному пути."""
    map_a = _bsl_relative_map(profile_a)
    map_b = _bsl_relative_map(profile_b)
    keys_a = set(map_a)
    keys_b = set(map_b)

    only_a = sorted(keys_a - keys_b)
    only_b = sorted(keys_b - keys_a)
    changed: list[dict] = []

    for rel in sorted(keys_a & keys_b):
        text_a = map_a[rel]
        text_b = map_b[rel]
        if text_a == text_b:
            continue
        diff_lines = list(
            difflib.unified_diff(
                text_a.splitlines(),
                text_b.splitlines(),
                fromfile=f"{profile_a}:{rel}",
                tofile=f"{profile_b}:{rel}",
                lineterm="",
            ),
        )
        added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
        changed.append({
            "path": rel,
            "lines_added": added,
            "lines_removed": removed,
            "diff_preview": "\n".join(diff_lines[:preview_lines]),
        })
        if len(changed) >= limit:
            break

    return {
        "only_in_a": only_a[:limit],
        "only_in_b": only_b[:limit],
        "changed": changed,
        "summary": {
            "bsl_files_a": len(map_a),
            "bsl_files_b": len(map_b),
            "only_a_count": len(only_a),
            "only_b_count": len(only_b),
            "changed_count": len(changed),
            "truncated": len(changed) >= limit,
        },
    }
