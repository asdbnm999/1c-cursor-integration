#!/usr/bin/env python3
"""CLI-обёртка. Основной способ — веб-интерфейс (kb-web)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.kb.indexer.profile_ops import create_profile  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Создать профиль (предпочтительно: kb-web)")
    parser.add_argument("--name", "-n", required=True)
    parser.add_argument("--display", "-d", default="")
    parser.add_argument("--format", "-f", choices=["edt", "xml_export"], required=True)
    parser.add_argument("--root", "-r", required=True)
    parser.add_argument("--src", default="src")
    parser.add_argument("--no-docs", action="store_true")
    args = parser.parse_args()

    path = create_profile(
        name=args.name,
        display_name=args.display or args.name,
        fmt=args.format,
        root=args.root,
        src=args.src,
        docs_enabled=not args.no_docs,
    )
    print(f"Создан: {path}")


if __name__ == "__main__":
    main()
