"""Интеграция статусов разделов §1–§4 для dashboard (ТЗ §6.4, шаг 7)."""

from __future__ import annotations

from typing import Any

from web.kb.service import compute_kb_section_status
from web.mcp.service import compute_section_status as compute_mcp_section_status
from web.mcp.service import get_standard_mcp_status
from web.plugins.service import get_plugins_status
from web.rules.service import compute_rules_section_status
from web.settings import load_settings, save_settings

SECTION_STATUS_LABELS = {
    "not_started": "Не начато",
    "in_progress": "В процессе",
    "ready": "Готово",
}

SECTION_META: dict[str, dict[str, str]] = {
    "plugins": {
        "title": "VS-плагины для 1С",
        "subtitle": "VS-плагины для 1С",
        "url": "/plugins/",
        "description": "Установка VSIX-расширений в Cursor: подсветка BSL и дерево конфигурации.",
        "doc_link": "/docs/01-plugins.md",
        "wizard_label": "Установить VS-плагины для 1С",
    },
    "mcp": {
        "title": "Стандартные MCP-серверы",
        "subtitle": "Стандартные MCP-серверы",
        "url": "/mcp/",
        "description": "Docker: SearXNG и 1C Syntax Helper для AI в Cursor.",
        "doc_link": "/docs/02-mcp-docker.md",
        "wizard_label": "Поднять стандартные MCP (SearXNG, Syntax)",
    },
    "kb": {
        "title": "Векторная база знаний проекта",
        "subtitle": "Векторная база знаний проекта",
        "url": "/kb/",
        "description": "Индексация EDT/XML и MCP-поиск по вашей конфигурации 1С.",
        "doc_link": "/docs/03-knowledge-base.md",
        "wizard_label": "Создать профиль векторной базы знаний",
    },
    "rules": {
        "title": "Генерация файла правил",
        "subtitle": "Генерация файла правил",
        "url": "/rules/",
        "description": "Markdown-регламент для AI из метаданных проекта 1С.",
        "doc_link": "/docs/04-rules-generator.md",
        "wizard_label": "Сгенерировать файл правил для AI",
    },
}

SECTION_ORDER = ("plugins", "mcp", "kb", "rules")

# U+2011 — дефис без переноса строки (обычный «-» браузер рвёт посередине).
_NB_HYPHEN = "\u2011"


def card_title_display(title: str) -> str:
    """Заголовок карточки dashboard: составные слова не разрываются по дефису."""
    return title.replace("-", _NB_HYPHEN)


def section_status_label(status: str) -> str:
    return SECTION_STATUS_LABELS.get(status, status)


def _compute_plugins_status() -> str:
    return get_plugins_status()["section_status"]


def _compute_mcp_status() -> str:
    return compute_mcp_section_status(get_standard_mcp_status(with_health=False))


def _compute_kb_status() -> str:
    return compute_kb_section_status()


def _compute_rules_status() -> str:
    settings = load_settings()
    last = settings.get("rules", {}).get("last_output") or {}
    return compute_rules_section_status(last)


_COMPUTERS = {
    "plugins": _compute_plugins_status,
    "mcp": _compute_mcp_status,
    "kb": _compute_kb_status,
    "rules": _compute_rules_status,
}


def refresh_all_section_statuses(*, persist: bool = True) -> dict[str, str]:
    """Пересчитать статусы всех разделов и опционально сохранить в settings."""
    statuses: dict[str, str] = {}
    for key in SECTION_ORDER:
        try:
            statuses[key] = _COMPUTERS[key]()
        except Exception:
            statuses[key] = load_settings().get("sections", {}).get(key, "not_started")

    if persist:
        settings = load_settings()
        sections = settings.setdefault("sections", {})
        changed = False
        for key, status in statuses.items():
            if sections.get(key) != status:
                sections[key] = status
                changed = True
        if changed:
            save_settings(settings)

    return statuses


def get_cached_section_statuses() -> dict[str, str]:
    """Быстрый снимок из settings без Docker/индексации."""
    settings = load_settings()
    stored = settings.get("sections", {})
    return {key: stored.get(key, "not_started") for key in SECTION_ORDER}


def build_sections_snapshot(*, refresh: bool = True) -> dict[str, Any]:
    """Полный снимок для dashboard и API."""
    if refresh:
        statuses = refresh_all_section_statuses(persist=True)
    else:
        statuses = get_cached_section_statuses()
    cards = []
    wizard_steps = []
    for index, key in enumerate(SECTION_ORDER, start=1):
        meta = SECTION_META[key]
        status = statuses[key]
        cards.append(
            {
                "id": key,
                "index": index,
                "title": card_title_display(meta["title"]),
                "url": meta["url"],
                "description": meta["description"],
                "doc_link": meta["doc_link"],
                "status": status,
                "status_label": section_status_label(status),
            }
        )
        wizard_steps.append(
            {
                "id": key,
                "index": index,
                "label": meta["wizard_label"],
                "url": meta["url"],
                "status": status,
                "status_label": section_status_label(status),
                "done": status == "ready",
            }
        )

    ready_count = sum(1 for s in statuses.values() if s == "ready")
    return {
        "sections": statuses,
        "cards": cards,
        "wizard_steps": wizard_steps,
        "summary": {
            "ready_count": ready_count,
            "total": len(SECTION_ORDER),
            "all_ready": ready_count == len(SECTION_ORDER),
        },
    }
