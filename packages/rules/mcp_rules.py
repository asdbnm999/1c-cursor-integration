"""Текст раздела MCP в генерируемых правилах (ТЗ §12.8)."""

from __future__ import annotations

from typing import Any


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
            "ревью через MCP `1c-syntax-helper` (проверка методов, параметров, существования API)."
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
                f"- **База знаний проекта:** использовать MCP `{key}` для поиска по метаданным "
                "и коду **этой** конфигурации."
            )
        else:
            keys = ", ".join(f"`{k}`" for k in kb_profiles)
            lines.append(
                f"- **Базы знаний проекта:** доступны MCP: {keys}. "
                "**В начале каждого диалога** спросить пользователя, какую базу использовать, "
                "если задача связана с кодом или метаданными конфигурации."
            )
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
