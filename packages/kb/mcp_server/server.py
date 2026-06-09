from __future__ import annotations

import argparse
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.embeddings import embed_query
from packages.kb.indexer.exceptions import IndexerError
from packages.kb.indexer.hybrid_search import hybrid_search
from packages.kb.indexer.module_reader import read_module
from packages.kb.indexer.object_detail import get_object_detail
from packages.kb.indexer.object_modules import list_object_modules as query_object_modules
from packages.kb.indexer.relations import list_by_relation as query_by_relation
from packages.kb.indexer.references import find_references as search_references
from packages.kb.indexer.store import get_by_metadata, query_chunks

_config: ProfileConfig | None = None
_mcp: FastMCP | None = None

PRIMARY_TOOLS = frozenset({
    "search_project",
    "get_object",
    "list_by_relation",
    "get_module",
    "find_references",
})


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


def _match_type(meta: dict[str, Any], snippet: str) -> str:
    kind = meta.get("kind", "")
    if kind == "metadata" or kind == "subsystem":
        return "metadata"
    if kind in ("bsl_procedure", "bsl_module_header"):
        upper = snippet.upper()
        if "ВЫБРАТЬ" in upper or "ЗАПРОС.ТЕКСТ" in upper or "РЕГИСТРНАКОПЛЕНИЯ" in upper:
            return "query_text"
        return "bsl"
    if "ВЫБРАТЬ" in snippet.upper():
        return "query_text"
    return "metadata"


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
        procedure = meta.get("procedure", "")
        snippet = doc.split("---", 1)[-1].strip()
        mtype = _match_type(meta, snippet)

        title = f"{object_type}.{object_name}"
        if procedure:
            title += f".{procedure}"

        lines.append(f"### {idx}. score={score} | {title}")
        lines.append(f"- Тип совпадения: {mtype}")
        lines.append(f"- Тип чанка: {meta.get('kind', '?')}")
        lines.append(f"- Путь: {path}")
        if meta.get("subsystems"):
            lines.append(f"- Подсистема: {meta.get('subsystems')}")
        if meta.get("is_export"):
            lines.append("- Экспорт: да")
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
        snippet = doc.split("---", 1)[-1].strip()
        mtype = _match_type(meta, snippet)
        title = f"{object_type}.{object_name}"
        lines.append(
            f"### {idx}. score={score} (vec={round(hit.get('vector_score', 0), 2)}, "
            f"kw={round(hit.get('keyword_score', 0), 2)}) | {title}"
        )
        lines.append(f"- Тип совпадения: {mtype}")
        lines.append(f"- Путь: {meta.get('path', '?')}")
        if len(snippet) > 600:
            snippet = snippet[:600] + "..."
        lines.append(f"- Фрагмент:\n```\n{snippet}\n```\n")
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
    def get_object(
        object_type: str,
        object_name: str,
        detail: str = "brief",
    ) -> str:
        """Карточка объекта метаданных. detail: brief | structure | movements | posting | full."""
        config = get_config()
        return get_object_detail(config, object_type, object_name, detail=detail)

    @mcp.tool()
    def list_by_relation(
        relation: str,
        object_type: str = "",
        object_name: str = "",
        limit: int = 50,
    ) -> str:
        """Связи объектов: documents_by_register, registers_by_document, references_to_object, objects_in_subsystem."""
        config = get_config()
        return query_by_relation(
            config,
            relation,
            object_type=object_type,
            object_name=object_name,
            limit=limit,
        )

    @mcp.tool()
    def get_module(
        module_path: str,
        mode: str = "summary",
        name: str = "",
        line_from: int = 0,
        line_to: int = 0,
    ) -> str:
        """Чтение BSL-модуля: summary | procedure | event | fragment."""
        config = get_config()
        try:
            return read_module(
                config,
                module_path,
                mode=mode,
                name=name,
                line_from=line_from,
                line_to=line_to,
            )
        except IndexerError as exc:
            return f"Ошибка: {exc}"

    @mcp.tool()
    def find_references(
        identifier: str,
        limit: int = 30,
        object_type: str = "",
        scope: str = "all",
    ) -> str:
        """Поиск ссылок на идентификатор. scope: all | metadata | bsl | queries."""
        config = get_config()
        try:
            refs = search_references(
                config,
                identifier,
                limit=limit,
                object_type=object_type,
                scope=scope,
            )
        except IndexerError as exc:
            return f"Ошибка: {exc}"
        if not refs:
            return f"Ссылки на «{identifier}» не найдены (scope={scope})."
        lines = [f"## Ссылки на «{identifier}» ({len(refs)})\n"]
        for r in refs:
            lines.append(
                f"- [{r.get('file_type', '?')}/{r.get('context_kind', '?')}] "
                f"{r['relative_path']}:{r['line']} — `{r['context'][:120]}`"
            )
        return "\n".join(lines)

    # --- Deprecated thin wrappers (переходный период) ---

    @mcp.tool()
    def get_register_movements(object_type: str, object_name: str) -> str:
        """DEPRECATED: используйте get_object(..., detail='movements')."""
        return get_object(object_type=object_type, object_name=object_name, detail="movements")

    @mcp.tool()
    def get_module_summary(module_path: str) -> str:
        """DEPRECATED: используйте get_module(mode='summary')."""
        return get_module(module_path=module_path, mode="summary")

    @mcp.tool()
    def list_object_modules(object_type: str, object_name: str) -> str:
        """DEPRECATED: используйте get_object(..., detail='full') или get_module."""
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
    def list_subsystems(subsystem_name: str = "") -> str:
        """DEPRECATED: используйте list_by_relation(relation='objects_in_subsystem')."""
        if subsystem_name:
            return list_by_relation(
                relation="objects_in_subsystem",
                object_name=subsystem_name,
            )
        config = get_config()
        where: dict[str, Any] = {"kind": "subsystem"}
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
    def search_by_subsystem(subsystem_name: str, limit: int = 20) -> str:
        """DEPRECATED: используйте list_by_relation или search_project с фильтром."""
        return list_by_relation(
            relation="objects_in_subsystem",
            object_name=subsystem_name,
            limit=limit,
        )


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

