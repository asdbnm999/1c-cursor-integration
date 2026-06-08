#!/usr/bin/env python3
"""Проверка качества поиска для профиля. Запросы задаются в profiles/<name>/queries.txt."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from packages.kb.indexer.config import load_config
from packages.kb.indexer.embeddings import embed_query
from packages.kb.indexer.profiles import profile_dir
from packages.kb.indexer.store import query_chunks


def load_queries(profile_name: str) -> list[str]:
    queries_file = profile_dir(profile_name) / "queries.txt"
    if not queries_file.exists():
        print(f"Создайте файл с запросами: {queries_file}")
        print("По одному запросу на строку.")
        sys.exit(1)
    return [
        line.strip()
        for line in queries_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", "-p", required=True)
    args = parser.parse_args()

    config = load_config(args.profile)
    queries = load_queries(config.profile_name)
    passed = 0

    print(f"Профиль: {config.profile_name}\n")
    for query in queries:
        embedding = embed_query(query, config.embeddings)
        results = query_chunks(config, embedding, limit=3)
        metas = results.get("metadatas", [[]])[0]
        print(f"Запрос: {query}")
        if not metas:
            print("  ❌ нет результатов\n")
            continue
        top = metas[0]
        title = f"{top.get('object_type')}.{top.get('object_name', '?')}"
        print(f"  → top-1: {title}\n")
        passed += 1

    print(f"С результатами: {passed}/{len(queries)}")


if __name__ == "__main__":
    main()
