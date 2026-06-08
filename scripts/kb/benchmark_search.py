#!/usr/bin/env python3
"""Бенчмарк поиска: hybrid vs vector, find_references."""

from __future__ import annotations

import argparse
import statistics
import time

from packages.kb.indexer.config import load_config
from packages.kb.indexer.hybrid_search import hybrid_search
from packages.kb.indexer.embeddings import embed_query
from packages.kb.indexer.references import find_references
from packages.kb.indexer.store import count_chunks, query_chunks


DEFAULT_QUERIES = [
    "проведение документа",
    "ТестовыйДокумент",
    "регистр накопления",
    "общий модуль",
    "справочник контрагент",
]


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = int(len(ordered) * p / 100)
    return ordered[min(idx, len(ordered) - 1)]


def bench(fn, *, runs: int = 5) -> dict:
    times: list[float] = []
    last_result = None
    for _ in range(runs):
        start = time.perf_counter()
        last_result = fn()
        times.append(time.perf_counter() - start)
    return {
        "runs": runs,
        "p50_ms": round(statistics.median(times) * 1000, 1),
        "p95_ms": round(_percentile(times, 95) * 1000, 1),
        "min_ms": round(min(times) * 1000, 1),
        "max_ms": round(max(times) * 1000, 1),
        "sample": str(last_result)[:80] if last_result is not None else "",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Бенчмарк search_project / find_references")
    parser.add_argument("--profile", "-p", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--query", action="append", dest="queries")
    args = parser.parse_args()

    config = load_config(args.profile)
    chunks = count_chunks(config)
    queries = args.queries or DEFAULT_QUERIES

    print(f"Профиль: {config.profile_name} · чанков: {chunks}")
    print(f"Запросов: {len(queries)} · прогонов на запрос: {args.runs}\n")

    for query in queries:
        print(f"=== «{query}» ===")

        hybrid = bench(
            lambda q=query: hybrid_search(config, q, limit=8),
            runs=args.runs,
        )
        print(f"  hybrid     p50={hybrid['p50_ms']}ms p95={hybrid['p95_ms']}ms")

        def vector_only(q=query):
            emb = embed_query(q, config.embeddings)
            return query_chunks(config, emb, limit=8)

        vector = bench(vector_only, runs=args.runs)
        print(f"  vector     p50={vector['p50_ms']}ms p95={vector['p95_ms']}ms")

        ident = query.split()[-1] if query.split() else query
        refs = bench(
            lambda i=ident: find_references(config, i, limit=20),
            runs=args.runs,
        )
        hits = len(find_references(config, ident, limit=20))
        print(f"  references p50={refs['p50_ms']}ms p95={refs['p95_ms']}ms hits={hits}")
        print()


if __name__ == "__main__":
    main()
