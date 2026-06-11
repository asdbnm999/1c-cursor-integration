"""Текст раздела MCP в генерируемых правилах (ТЗ §12.8)."""

from __future__ import annotations

from typing import Any

# Синхронизировать с packages/kb/mcp_server/server.py → MCP_TOOLS
KB_MCP_TOOLS = (
    "search_project",
    "get_object",
    "list_by_relation",
    "get_module",
    "find_references",
)

KB_MCP_DEPRECATED_TOOLS = (
    "get_register_movements",
    "get_module_summary",
    "list_object_modules",
    "list_subsystems",
    "search_by_subsystem",
)


def _build_kb_tools_section(kb_profiles: list[str]) -> list[str]:
    """Блок tools MCP базы знаний (только при включённом KB-профиле)."""
    if not kb_profiles:
        return []

    multi = len(kb_profiles) > 1
    server = kb_profiles[0] if not multi else "1c-kb-…"

    lines: list[str] = [""]

    if multi:
        lines.extend(
            [
                "  После выбора базы вызывать tools **выбранного** MCP-сервера (`1c-kb-…`).",
                "",
            ]
        )

    lines.extend(
        [
            f"  **Инструменты MCP `{server}` ({len(KB_MCP_TOOLS)} методов):**",
            "",
            "  | Tool | Когда вызывать |",
            "  |------|----------------|",
            "  | `search_project` | Не знаешь точное имя объекта; поиск по смыслу по всей конфигурации |",
            "  | `get_object` | Карточка объекта: структура, движения, проведение |",
            "  | `list_by_relation` | Обратные связи: кто двигает регистр, что в подсистеме |",
            "  | `get_module` | Точечное чтение BSL: процедура, обработчик, фрагмент |",
            "  | `find_references` | Где используется идентификатор (процедура, регистр, реквизит) |",
            "",
            "  **Параметры ключевых tools:**",
            "",
            "  - `search_project(query, limit=8, object_type=\"\", hybrid=true)` — в ответе тип совпадения: "
            "`metadata` / `bsl` / `query_text`",
            "  - `get_object(object_type, object_name, detail=\"brief\")` — `detail`: `brief` | `structure` | "
            "`movements` | `posting` | `full`",
            "  - `list_by_relation(relation, object_type=\"\", object_name=\"\", limit=50)` — `relation`: "
            "`documents_by_register` | `registers_by_document` | `references_to_object` | `objects_in_subsystem`",
            "  - `get_module(module_path, mode=\"summary\", name=\"\", line_from=0, line_to=0)` — `mode`: "
            "`summary` | `procedure` | `event` | `fragment`",
            "  - `find_references(identifier, limit=30, object_type=\"\", scope=\"all\")` — `scope`: `all` | "
            "`metadata` | `bsl` | `queries`",
            "",
            "  **Матрица «вопрос → tool»:**",
            "",
            "  | Вопрос пользователя | Tool | Параметры |",
            "  |---------------------|------|-----------|",
            "  | Где в конфигурации про X? | `search_project` | `query` |",
            "  | Что за объект? | `get_object` | `detail=\"brief\"` |",
            "  | Реквизиты, ТЧ, измерения регистра? | `get_object` | `detail=\"structure\"` |",
            "  | Какие регистры двигает документ? | `get_object` | `detail=\"movements\"` |",
            "  | Как проводится документ? | `get_object` | `detail=\"posting\"` |",
            "  | Кто двигает регистр? | `list_by_relation` | `relation=\"documents_by_register\"` |",
            "  | Что входит в подсистему? | `list_by_relation` | `relation=\"objects_in_subsystem\"` |",
            "  | Где используется имя/процедура? | `find_references` | `identifier`, при необходимости `scope` |",
            "  | Покажи процедуру или обработчик | `get_module` | `mode=\"procedure\"` или `mode=\"event\"`, `name=...` |",
            "",
            "  **Разделение ролей MCP (не смешивать):**",
            f"  - KB (`{server}`) — структура и код **этой конфигурации** (метаданные, BSL, запросы, связи).",
            "  - `1c-syntax-helper` — синтаксис **платформы** 1С (`Новый Запрос`, `ВидДвиженияНакопления`, "
            "методы глобального контекста).",
            "  - `searxng` — только веб-поиск (статьи, релизы, интеграции).",
            "",
            "  **Запрещено для задач по конфигурации:** угадывать состав метаданных; читать XML/BSL целиком "
            "«с диска», если есть tool KB; вызывать устаревшие имена "
            f"({', '.join(f'`{t}`' for t in KB_MCP_DEPRECATED_TOOLS)}) — их в MCP больше нет.",
        ]
    )

    return lines


def build_mcp_rules_section(mcp: dict[str, Any]) -> str:
    """
    mcp: {
      searxng: bool,
      syntax_helper: bool,
      kb_profiles: list[str],  # включённые ключи 1c-kb-*
    }
    """
    searxng = bool(mcp.get("searxng"))
    syntax = bool(mcp.get("syntax_helper"))
    kb_profiles = [str(p) for p in (mcp.get("kb_profiles") or []) if p]

    lines = [
        "",
        "## MCP-серверы Cursor",
        "",
        "> Настройки согласованы с `mcp.json` Cursor на момент генерации правил.",
        "",
    ]

    if searxng:
        lines.append(
            "- **Веб-поиск:** весь веб-поиск **без исключения** выполнять через MCP `searxng` "
            "(локальный SearXNG). Не использовать встроенный web search Cursor и не искать в интернете "
            "в обход MCP."
        )
    else:
        lines.append(
            "- **Веб-поиск (SearXNG):** сервер недоступен или отключён в настройках правил — "
            "**не использовать** для поиска в интернете."
        )

    if syntax:
        lines.append(
            "- **Справка платформы 1С:** после написания или изменения кода 1С — **обязательное** "
            "ревью через MCP `1c-syntax-helper` (проверка методов, параметров, существования API). "
            "Для синтаксиса платформы — **не** KB."
        )
    else:
        lines.append(
            "- **1C Syntax Helper:** недоступен или отключён — не полагаться на память модели; "
            "при сомнениях уточнять у пользователя."
        )

    if kb_profiles:
        if len(kb_profiles) == 1:
            key = kb_profiles[0]
            lines.append(
                f"- **База знаний проекта:** использовать MCP `{key}` для работы с метаданными "
                "и кодом **этой** конфигурации. Не парсить XML/BSL вручную, если ответ можно получить "
                "через tools ниже."
            )
        else:
            keys = ", ".join(f"`{k}`" for k in kb_profiles)
            lines.append(
                f"- **Базы знаний проекта:** доступны MCP: {keys}. "
                "**В начале каждого диалога** спросить пользователя, какую базу использовать, "
                "если задача связана с кодом или метаданными конфигурации."
            )
        lines.extend(_build_kb_tools_section(kb_profiles))
    else:
        lines.append(
            "- **База знаний проекта (KB):** не подключена — не выдумывать структуру конфигурации; "
            "опираться только на открытые файлы и контекст задачи."
        )

    lines.append("")
    return "\n".join(lines)


def mcp_toggles_from_status(
    status: dict[str, Any],
    *,
    user_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Собрать toggles для UI: defaults из live mcp.json + override пользователя."""
    servers = status.get("servers") or {}
    overrides = user_overrides or {}

    kb_keys = sorted(k for k in servers if k.startswith("1c-kb-"))

    def _default_enabled(key: str) -> bool:
        return key in servers

    searxng = overrides.get("searxng")
    if searxng is None:
        searxng = _default_enabled("searxng")
    syntax = overrides.get("syntax_helper")
    if syntax is None:
        syntax = _default_enabled("1c-syntax-helper")

    kb_selected = overrides.get("kb_profiles")
    if kb_selected is None:
        kb_selected = kb_keys
    elif isinstance(kb_selected, dict):
        kb_selected = [k for k, on in kb_selected.items() if on]
    elif not isinstance(kb_selected, list):
        kb_selected = kb_keys

    return {
        "searxng": bool(searxng),
        "syntax_helper": bool(syntax),
        "kb_profiles": list(kb_selected),
        "available": {
            "searxng": "searxng" in servers,
            "syntax_helper": "1c-syntax-helper" in servers,
            "kb_profiles": kb_keys,
        },
    }
