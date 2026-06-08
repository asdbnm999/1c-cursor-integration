#!/usr/bin/env python3
"""Одноразовый скрипт: indexer/mcp_server → packages.kb.* (шаг 2A)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET_DIRS = [
    ROOT / "packages" / "kb",
    ROOT / "tests" / "kb",
    ROOT / "scripts" / "kb",
]

REPLACEMENTS = [
    (re.compile(r"\bfrom indexer\."), "from packages.kb.indexer."),
    (re.compile(r"\bimport indexer\."), "import packages.kb.indexer."),
    (re.compile(r"\bfrom mcp_server\."), "from packages.kb.mcp_server."),
    (re.compile(r"\bimport mcp_server\."), "import packages.kb.mcp_server."),
]


def rewrite_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    for pattern, repl in REPLACEMENTS:
        text = pattern.sub(repl, text)
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> None:
    changed = 0
    for base in TARGET_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if rewrite_file(path):
                changed += 1
                print(f"  {path.relative_to(ROOT)}")
    print(f"Updated {changed} files")


if __name__ == "__main__":
    main()
