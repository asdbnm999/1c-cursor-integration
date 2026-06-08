from __future__ import annotations

import argparse
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.embeddings import embed_query
from packages.kb.indexer.exceptions import IndexerError
from packages.kb.indexer.extract_bsl import extract_bsl_procedures
from packages.kb.indexer.hybrid_search import hybrid_search
from packages.kb.indexer.object_modules import list_object_modules as query_object_modules
from packages.kb.indexer.references import find_references as search_references
from packages.kb.indexer.store import get_by_metadata, query_chunks

_config: ProfileConfig | None = None
_mcp: FastMCP | None = None


def get_config() -> ProfileConfig:
    global _config
    if _config is None:
        raise RuntimeError("Конфигурация не загружена. Укажите --profile.")
    return _config


def get_mcp() -> FastMCP:
    global _mcp
    if _mcp is None:
        import os

        cfg = get_config()
        port = 8000 if os.environ.get("KB_PROFILE") else cfg.mcp.port
        host = cfg.mcp.host or "0.0.0.0"
        _mcp = FastMCP(cfg.mcp.server_name, host=host, port=port)
        _register_tools(_mcp)
    return _mcp


def _score_from_distance(distance: float | None) -> float:
    if distance is None:
        return 0.0
    return round(max(0.0, 1.0 - distance), 3)


def format_search_results(results: dict[str, Any], limit: int) -> str:
    docs = results.get("documents", [[]])[0]
    metas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]
    if not docs:
        return "Результаты не найдены."

    lines = [f"Найдено результатов: {min(len(docs), limit)}\n"]
    for idx, (doc, meta, distance) in enumerate(zip(docs, metas, distances), start=1):
        score = _score_from_distance(distance)
        object_type = meta.get("object_type", "?")
        object_name = meta.get("object_name", meta.get("module", "?"))
        path = meta.get("path", "?")
        kind = meta.get("kind", "?")
        procedure = meta.get("procedure", "")

        title = f"{object_type}.{object_name}"
        if procedure:
            title += f".{procedure}"

        lines.append(f"### {idx}. score={score} | {title}")
        lines.append(f"- Тип чанка: {kind}")
        lines.append(f"- Путь: {path}")
        if meta.get("subsystems"):
            lines.append(f"- Подсистема: {meta.get('subsystems')}")
        if meta.get("is_export"):
            lines.append("- Экспорт: да")
        snippet = doc.split("---", 1)[-1].strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        lines.append(f"- Фрагмент:\n```\n{snippet}\n```\n")
    return "\n".join(lines)


def format_hybrid_results(hits: list[dict[str, Any]], limit: int) -> str:
    if not hits:
        return "Результаты не найдены."
    lines = [f"Найдено (гибридный поиск): {len(hits)}\n"]
    for idx, hit in enumerate(hits[:limit], start=1):
        meta = hit.get("metadata", {})
        doc = hit.get("document", "")
        score = round(hit.get("combined_score", 0), 3)
        object_type = meta.get("object_type", "?")
        object_name = meta.get("object_name", meta.get("module", "?"))
        title = f"{object_type}.{object_name}"
        lines.append(
            f"### {idx}. score={score} (vec={round(hit.get('vector_score', 0), 2)}, "
            f"kw={round(hit.get('keyword_score', 0), 2)}) | {title}"
        )
        lines.append(f"- Путь: {meta.get('path', '?')}")
        snippet = doc.split("---", 1)[-1].strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        lines.append(f"- Фрагмент:\n```\n{snippet}\n```\n")
    return "\n".join(lines)


def format_object_card(results: dict[str, Any]) -> str:
    docs = results.get("documents", [])
    metas = results.get("metadatas", [])
    if not docs:
        return "Объект не найден в базе знаний."
    lines = ["## Карточка объекта\n"]
    for doc, meta in zip(docs, metas):
        lines.append(f"### {meta.get('object_type')}.{meta.get('object_name')}")
        lines.append(f"- Путь: {meta.get('path')}")
        if meta.get("subsystems"):
            lines.append(f"- Подсистемы: {meta.get('subsystems')}")
        lines.append("")
        lines.append(doc)
        lines.append("")
    return "\n".join(lines)


def _register_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_project(
        query: str,
        limit: int = 8,
        object_type: str = "",
        hybrid: bool = True,
    ) -> str:
        """Семантический (и гибридный) поиск по базе знаний проекта 1С."""
        config = get_config()
        if limit <= 0:
            limit = config.mcp.default_search_limit
        if hybrid:
            hits = hybrid_search(config, query, limit=limit, object_type=object_type)
            return format_hybrid_results(hits, limit)
        embedding = embed_query(query, config.embeddings)
        where: dict[str, Any] | None = {"object_type": object_type} if object_type else None
        results = query_chunks(config, embedding, limit=limit, where=where)
        return format_search_results(results, limit)

    @mcp.tool()
    def get_object(object_type: str, object_name: str) -> str:
        """Карточка объекта метаданных по точному имени."""
        config = get_config()
        where: dict[str, Any] = {
            "$and": [
                {"kind": "metadata"},
                {"object_type": object_type},
                {"object_name": object_name},
            ]
        }
        results = get_by_metadata(config, where=where)
        return format_object_card(results)

    @mcp.tool()
    def get_module_summary(module_path: str) -> str:
        """Сводка по BSL-модулю: заголовок и экспортные процедуры."""
        procedures = extract_bsl_procedures(module_path)
        exports = [p for p in procedures if p.is_export]
        lines = [f"## Модуль: {module_path}", f"Всего процедур/функций: {len(procedures)}", ""]
        if exports:
            lines.append("### Экспортные методы")
            for proc in exports:
                region = f" [{proc.region}]" if proc.region else ""
                lines.append(f"- {proc.signature}{region}")
        else:
            lines.append("Экспортные методы не найдены.")
        return "\n".join(lines)

    @mcp.tool()
    def list_subsystems(subsystem_name: str = "") -> str:
        """Список подсистем и входящих объектов из индекса."""
        config = get_config()
        where: dict[str, Any] = (
            {"$and": [{"kind": "subsystem"}, {"object_name": subsystem_name}]}
            if subsystem_name
            else {"kind": "subsystem"}
        )
        results = get_by_metadata(config, where=where)
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        if not docs:
            return "Подсистемы не найдены в индексе."
        lines = ["## Подсистемы\n"]
        for doc, meta in zip(docs, metas):
            lines.append(f"### {meta.get('object_name')}")
            lines.append(f"- Путь: {meta.get('path')}")
            if meta.get("parent"):
                lines.append(f"- Родитель: {meta.get('parent')}")
            lines.append(doc.split("---", 1)[-1].strip()[:800])
            lines.append("")
        return "\n".join(lines)

    @mcp.tool()
    def find_references(identifier: str, limit: int = 30, object_type: str = "") -> str:
        """Поиск ссылок на идентификатор (процедура, регистр, документ) в BSL-модулях."""
        config = get_config()
        try:
            refs = search_references(config, identifier, limit=limit, object_type=object_type)
        except IndexerError as exc:
            return f"Ошибка: {exc}"
        if not refs:
            return f"Ссылки на «{identifier}» не найдены."
        lines = [f"## Ссылки на «{identifier}» ({len(refs)})\n"]
        for r in refs:
            lines.append(f"- {r['relative_path']}:{r['line']} — `{r['context'][:120]}`")
        return "\n".join(lines)

    @mcp.tool()
    def list_object_modules(object_type: str, object_name: str) -> str:
        """Список BSL-модулей объекта метаданных."""
        config = get_config()
        try:
            modules = query_object_modules(config, object_type, object_name)
        except IndexerError as exc:
            return f"Ошибка: {exc}"
        if not modules:
            return f"Модули для {object_type}.{object_name} не найдены."
        lines = [f"## Модули {object_type}.{object_name}\n"]
        for m in modules:
            lines.append(f"- **{m['name']}** ({m['kind']}): `{m['relative_path']}`")
        return "\n".join(lines)

    @mcp.tool()
    def search_by_subsystem(subsystem_name: str, limit: int = 20) -> str:
        """Поиск объектов и чанков, относящихся к подсистеме."""
        config = get_config()
        collection_results = get_by_metadata(
            config,
            where={"kind": "subsystem", "object_name": subsystem_name},
        )
        docs = collection_results.get("documents", [])
        if not docs:
            return f"Подсистема «{subsystem_name}» не найдена в индексе."

        lines = [f"## Подсистема: {subsystem_name}\n", docs[0].split("---", 1)[-1].strip()[:1000], ""]

        all_data = get_by_metadata(config, where={"kind": "metadata"})
        metas = all_data.get("metadatas", [])
        all_docs = all_data.get("documents", [])
        matched = 0
        for doc, meta in zip(all_docs, metas):
            subs = meta.get("subsystems", "")
            if subsystem_name in subs.split(","):
                matched += 1
                if matched <= limit:
                    lines.append(f"- {meta.get('object_type')}.{meta.get('object_name')}")
        lines.append(f"\nВсего объектов в подсистеме: {matched}")
        return "\n".join(lines)

    @mcp.tool()
    def get_register_movements(object_type: str, object_name: str) -> str:
        """Движения по регистрам для документа/объекта из индекса метаданных."""
        config = get_config()
        where: dict[str, Any] = {
            "$and": [
                {"kind": "metadata"},
                {"object_type": object_type},
                {"object_name": object_name},
            ]
        }
        results = get_by_metadata(config, where=where)
        docs = results.get("documents", [])
        metas = results.get("metadatas", [])
        if not docs:
            return f"Объект {object_type}.{object_name} не найден."

        meta = metas[0] if metas else {}
        records_raw = meta.get("register_records", "")
        if records_raw:
            records = [r.strip() for r in str(records_raw).split(",") if r.strip()]
            if records:
                lines = [f"## Движения по регистрам: {object_type}.{object_name}\n"]
                lines.extend(f"- {r}" for r in records)
                return "\n".join(lines)

        text = docs[0]
        if "Движения по регистрам:" not in text:
            return f"У {object_type}.{object_name} нет движений по регистрам в индексе."
        section = text.split("Движения по регистрам:", 1)[1].strip()
        return f"## Движения по регистрам: {object_type}.{object_name}\n\n{section[:2000]}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="MCP-сервер 1C project KB")
    parser.add_argument("--profile", "-p", required=True, help="Имя профиля")
    parser.add_argument("--transport", choices=["stdio", "http"], default=None)
    parser.add_argument("--port", type=int, default=None)
    args = parser.parse_args(argv)

    global _config
    _config = load_config(args.profile)
    mcp = get_mcp()

    transport = args.transport or _config.mcp.transport
    if transport == "http":
        mcp.run(transport="streamable-http")
    else:
        mcp.run()


def main_deprecated() -> None:
    print("kb-mcp устарел; используйте 1c-cursor-kb-mcp.", file=sys.stderr)
    main()


if __name__ == "__main__":
    main(sys.argv[1:])
