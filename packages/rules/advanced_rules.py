"""Дополнительные правила для .md: да/нет и варианты — через UI, не [ЗАПОЛНИТЬ] в тексте."""

from __future__ import annotations

from typing import Any

# Не попадает в файл правил — в .md остаётся общая формулировка без жёсткого выбора
ADVANCED_SKIP_LABEL = "— не включать в файл —"


def _choice_field(
    key: str,
    label: str,
    options: tuple[str, ...],
    *,
    section: str,
    recommended: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "section": section,
        "field_type": "choice",
        "options": (ADVANCED_SKIP_LABEL, *options),
        "recommended": recommended,
    }


ADVANCED_RULE_SPECS: list[dict[str, Any]] = [
    _choice_field(
        "xml_change_uuid",
        "Менять UUID объектов без явного указания в задаче",
        ("да", "нет"),
        section="XML-выгрузка",
        recommended="нет",
    ),
    _choice_field(
        "xml_touch_config_files",
        "Трогать ConfigDumpInfo.xml и Configuration.xml без необходимости",
        ("да", "нет"),
        section="XML-выгрузка",
        recommended="нет",
    ),
    _choice_field(
        "xml_preserve_element_order",
        "Сохранять порядок элементов в XML как в выгрузке",
        ("да", "нет"),
        section="XML-выгрузка",
        recommended="да",
    ),
    _choice_field(
        "xml_new_uuid_on_add",
        "При добавлении объектов — генерировать новые UUID",
        ("да", "нет"),
        section="XML-выгрузка",
        recommended="да",
    ),
    _choice_field(
        "xml_create_metadata",
        "Самостоятельное создание объектов метаданных",
        ("да", "нет", "с разрешения"),
        section="XML-выгрузка",
        recommended="с разрешения",
    ),
    _choice_field(
        "edt_create_metadata",
        "Самостоятельное создание объектов метаданных (EDT)",
        ("да", "нет", "с разрешения"),
        section="EDT-проект",
        recommended="с разрешения",
    ),
    _choice_field(
        "bsl_edit_only_bsl_files",
        "Редактировать только отдельные .bsl, не встраивать код только в XML",
        ("да", "нет"),
        section="Модули .bsl",
        recommended="да",
    ),
    _choice_field(
        "arch_use_extensions",
        "Использовать расширения конфигурации для доработок",
        ("да", "нет", "когда указано в задаче"),
        section="Архитектура",
        recommended="когда указано в задаче",
    ),
    _choice_field(
        "arch_use_bsp",
        "Использовать функции БСП, где уместно",
        ("да", "нет"),
        section="Архитектура",
        recommended="да",
    ),
    _choice_field(
        "tx_try_except",
        "Использование Попытка / Исключение",
        ("только где нужно", "избегать", "по ситуации"),
        section="Транзакции и ошибки",
        recommended="только где нужно",
    ),
    _choice_field(
        "tx_user_messages",
        "Сообщения пользователю при ошибках",
        ("да", "нет"),
        section="Транзакции и ошибки",
        recommended="да",
    ),
    _choice_field(
        "tx_event_log",
        "Запись в журнал регистрации",
        ("да", "нет"),
        section="Журнал регистрации",
        recommended="да",
    ),
    _choice_field(
        "perf_prefer_queries",
        "Предпочитать запросы вместо обхода коллекций в цикле",
        ("да", "нет"),
        section="Запросы",
        recommended="да",
    ),
    _choice_field(
        "perf_temp_tables",
        "Временные таблицы в запросах",
        ("когда нужно", "избегать"),
        section="Запросы",
        recommended="когда нужно",
    ),
    _choice_field(
        "int_http_reuse",
        "HTTP-соединения — переиспользовать",
        ("да", "нет"),
        section="Интеграции",
        recommended="да",
    ),
    _choice_field(
        "ban_change_typical",
        "Менять типовые объекты без согласования",
        ("да", "нет"),
        section="Запреты",
        recommended="нет",
    ),
    _choice_field(
        "ban_delete_metadata",
        "Удалять объекты метаданных",
        ("да", "нет"),
        section="Запреты",
        recommended="нет",
    ),
    _choice_field(
        "ban_change_roles",
        "Менять права и роли без запроса",
        ("да", "нет"),
        section="Запреты",
        recommended="нет",
    ),
]

ADVANCED_RULE_KEYS = frozenset(s["key"] for s in ADVANCED_RULE_SPECS)

# Только отдельный .md, не дублировать в основном файле правил
ADVANCED_EVENT_LOG_KEYS = frozenset({"tx_event_log"})

# Общие формулировки в .md, если поле не задано в UI
ADVANCED_GENERIC: dict[str, str] = {
    "xml_change_uuid": "UUID объектов — только по явному указанию в задаче.",
    "xml_touch_config_files": "Служебные файлы корня выгрузки — только при необходимости задачи.",
    "xml_preserve_element_order": "Сохранять привычную структуру XML выгрузки.",
    "xml_new_uuid_on_add": "Для новых объектов — корректные уникальные идентификаторы.",
    "xml_create_metadata": (
        "Новые объекты метаданных — только при явном разрешении в задаче."
    ),
    "edt_create_metadata": (
        "Новые объекты метаданных в EDT — только при явном разрешении в задаче."
    ),
    "bsl_edit_only_bsl_files": "Код модулей — в файлах `.bsl` выгрузки.",
    "arch_use_extensions": "Расширения — по договорённости проекта и формулировке задачи.",
    "arch_use_bsp": "Повторно использовать типовые механизмы платформы и БСП, где уместно.",
    "tx_try_except": "Обработку исключений — осмысленно, без лишних пустых блоков.",
    "tx_user_messages": "Ошибки пользователю — понятно, без лишних технических деталей.",
    "tx_event_log": "Журнал регистрации — по отдельному файлу правил (см. рядом с основным).",
    "perf_prefer_queries": "Предпочитать запросы там, где это читаемее и быстрее.",
    "perf_temp_tables": "Временные таблицы — по необходимости объёма данных.",
    "int_http_reuse": "Внешние вызовы — с учётом повторного использования соединений.",
    "ban_change_typical": "Типовые объекты — не менять без явного согласования.",
    "ban_delete_metadata": "Удаление объектов метаданных — только по запросу.",
    "ban_change_roles": "Права и роли — только по запросу.",
}


def serialize_advanced_specs() -> list[dict[str, Any]]:
    return [
        {
            "key": s["key"],
            "label": s["label"],
            "section": s["section"],
            "field_type": s["field_type"],
            "options": list(s["options"]),
            "recommended": s["recommended"],
        }
        for s in ADVANCED_RULE_SPECS
    ]


def recommended_advanced_defaults() -> dict[str, str]:
    return {s["key"]: s["recommended"] for s in ADVANCED_RULE_SPECS}


def advanced_modal_initial_defaults() -> dict[str, str]:
    """Variant A (ТЗ §12.7): первое открытие modal — create_metadata = «нет», остальное — skip."""
    out = {s["key"]: ADVANCED_SKIP_LABEL for s in ADVANCED_RULE_SPECS}
    out["xml_create_metadata"] = "нет"
    out["edt_create_metadata"] = "нет"
    return out


def advanced_to_overrides(raw: dict[str, str] | None) -> dict[str, str]:
    """Значения для генератора: только явно выбранные (не «не включать»)."""
    if not raw:
        return {}
    out: dict[str, str] = {}
    for key, value in raw.items():
        if key not in ADVANCED_RULE_KEYS:
            continue
        v = (value or "").strip()
        if not v or v == ADVANCED_SKIP_LABEL:
            continue
        out[key] = v
    return out
