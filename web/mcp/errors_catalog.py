"""Статический каталог ошибок + подсветка в логах (ТЗ §10.7)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from web.paths import DOCS_DIR

CATALOG_PATH = DOCS_DIR / "errors" / "mcp-docker.json"


def load_catalog() -> list[dict[str, Any]]:
    if not CATALOG_PATH.is_file():
        return []
    data = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return list(data.get("errors") or [])


def match_errors_in_logs(logs: str, catalog: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    items = catalog or load_catalog()
    hits = []
    for entry in items:
        pattern = entry.get("log_pattern") or entry.get("symptom_regex")
        if not pattern:
            continue
        try:
            if re.search(pattern, logs, re.IGNORECASE | re.MULTILINE):
                hits.append(entry)
        except re.error:
            continue
    return hits


def build_error_help(server: str, logs: str) -> dict[str, Any]:
    catalog = load_catalog()
    matched = match_errors_in_logs(logs, catalog)
    server_entries = [e for e in catalog if not e.get("server") or e.get("server") == server]
    return {
        "server": server,
        "static": server_entries,
        "matched": matched,
        "logs_excerpt": logs[-8000:] if logs else "",
        "catalog_path": str(CATALOG_PATH),
    }
