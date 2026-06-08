"""Гибридный поиск: вектор + ключевые слова (BM25-подобный скоринг)."""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.embeddings import embed_query
from packages.kb.indexer.keyword_index import load_keyword_documents
from packages.kb.indexer.store import get_collection, query_chunks

logger = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\wА-Яа-яЁё]+", re.UNICODE)
_STOP = frozenset(
    "и в на с по для из к от а но или как что это не при быть".split()
)


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN_RE.findall(text) if len(t) > 1]
    return [t for t in tokens if t not in _STOP]


def _bm25_score(query_tokens: list[str], doc_text: str, avg_dl: float, df: Counter, n_docs: int) -> float:
    if not query_tokens:
        return 0.0
    doc_tokens = tokenize(doc_text)
    if not doc_tokens:
        return 0.0
    tf = Counter(doc_tokens)
    dl = len(doc_tokens)
    k1, b = 1.5, 0.75
    score = 0.0
    for term in query_tokens:
        if term not in tf:
            continue
        freq = tf[term]
        doc_freq = df.get(term, 0)
        idf = math.log(1 + (n_docs - doc_freq + 0.5) / (doc_freq + 0.5))
        denom = freq + k1 * (1 - b + b * dl / max(avg_dl, 1))
        score += idf * (freq * (k1 + 1)) / denom
    return score


def _vector_score(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return max(0.0, 1.0 - distance)


def hybrid_search(
    config: ProfileConfig,
    query: str,
    *,
    limit: int = 8,
    object_type: str = "",
    vector_weight: float | None = None,
    keyword_weight: float | None = None,
) -> list[dict[str, Any]]:
    """Объединяет семантический и ключевой поиск с нормализацией скоров."""
    if limit <= 0:
        limit = config.mcp.default_search_limit

    vw = vector_weight if vector_weight is not None else config.search.vector_weight
    kw = keyword_weight if keyword_weight is not None else config.search.keyword_weight

    where: dict[str, Any] | None = {"object_type": object_type} if object_type else None
    embedding = embed_query(query, config.embeddings)
    vector_results = query_chunks(config, embedding, limit=limit * 3, where=where)

    docs_v = vector_results.get("documents", [[]])[0]
    metas_v = vector_results.get("metadatas", [[]])[0]
    dists_v = vector_results.get("distances", [[]])[0]
    ids_v = vector_results.get("ids", [[]])[0]

    query_tokens = tokenize(query)
    keyword_hits: list[tuple[str, str, dict, float]] = []
    if query_tokens:
        try:
            indexed_docs = load_keyword_documents(config)
            if indexed_docs:
                k_docs = [d["text"] for d in indexed_docs]
                k_metas = [d.get("metadata") or {} for d in indexed_docs]
                k_ids = [d["id"] for d in indexed_docs]
                if object_type:
                    filtered = [
                        (cid, doc, meta)
                        for cid, doc, meta in zip(k_ids, k_docs, k_metas)
                        if meta.get("object_type") == object_type
                    ]
                    if filtered:
                        k_ids, k_docs, k_metas = zip(*filtered)
                        k_ids, k_docs, k_metas = list(k_ids), list(k_docs), list(k_metas)
                    else:
                        k_docs, k_metas, k_ids = [], [], []
            else:
                collection = get_collection(config)
                all_data = collection.get(
                    where=where,
                    include=["documents", "metadatas"],
                    limit=min(5000, max(limit * 50, 200)),
                )
                k_docs = all_data.get("documents") or []
                k_metas = all_data.get("metadatas") or []
                k_ids = all_data.get("ids") or []
                if not indexed_docs:
                    logger.warning(
                        "Keyword index отсутствует для %s — fallback на sample Chroma (%d docs)",
                        config.profile_name,
                        len(k_docs),
                    )

            if k_docs:
                avg_dl = sum(len(tokenize(d)) for d in k_docs) / max(len(k_docs), 1)
                df: Counter = Counter()
                for doc in k_docs:
                    df.update(set(tokenize(doc)))
                n_docs = len(k_docs)
                for cid, doc, meta in zip(k_ids, k_docs, k_metas):
                    kw_score = _bm25_score(query_tokens, doc, avg_dl, df, n_docs)
                    if kw_score > 0:
                        keyword_hits.append((cid, doc, meta, kw_score))
                keyword_hits.sort(key=lambda x: x[3], reverse=True)
        except Exception as exc:
            logger.warning("Keyword search failed for %s: %s", config.profile_name, exc)
            keyword_hits = []

    merged: dict[str, dict[str, Any]] = {}

    max_kw = max((h[3] for h in keyword_hits), default=1.0) or 1.0
    for cid, doc, meta, dist in zip(ids_v, docs_v, metas_v, dists_v):
        vs = _vector_score(dist)
        merged[cid] = {
            "id": cid,
            "document": doc,
            "metadata": meta,
            "vector_score": vs,
            "keyword_score": 0.0,
            "combined_score": vs * vw,
        }

    for cid, doc, meta, kw_hit in keyword_hits[: limit * 3]:
        ks = kw_hit / max_kw
        if cid in merged:
            merged[cid]["keyword_score"] = ks
            merged[cid]["combined_score"] = (
                merged[cid]["vector_score"] * vw + ks * kw
            )
        else:
            merged[cid] = {
                "id": cid,
                "document": doc,
                "metadata": meta,
                "vector_score": 0.0,
                "keyword_score": ks,
                "combined_score": ks * kw,
            }

    ranked = sorted(merged.values(), key=lambda x: x["combined_score"], reverse=True)
    return ranked[:limit]
