"""Анализ BSL: движения по регистрам, обработчики проведения, запросы."""

from __future__ import annotations

import re
from typing import Any

from packages.kb.indexer.extract_bsl import extract_bsl_procedures

MOVEMENT_ADD_RE = re.compile(
    r"Движения\.([\wА-Яа-яЁё]+)\.Добавить\s*\(",
    re.UNICODE,
)
MOVEMENT_KIND_RE = re.compile(
    r"ВидДвижения(?:Накопления)?\.([\wА-Яа-яЁё]+)",
    re.UNICODE,
)
REGISTER_QUERY_RE = re.compile(
    r"Регистр(?:Накопления|Сведений|Бухгалтерии)\.([\wА-Яа-яЁё]+)",
    re.UNICODE,
)
QUERY_TEXT_RE = re.compile(
    r'Запрос\.Текст\s*=\s*"(.*?)"',
    re.DOTALL | re.UNICODE,
)
EVENT_HANDLERS = frozenset({
    "ОбработкаПроведения",
    "ОбработкаУдаленияПроведения",
    "ПередЗаписью",
    "ПриЗаписи",
    "ПередУдалением",
    "ОбработкаЗаполнения",
    "ОбработкаПроверкиЗаполнения",
})


def _movement_kind_ru(kind: str) -> str:
    mapping = {
        "Receipt": "Приход",
        "Expense": "Расход",
        "Приход": "Приход",
        "Расход": "Расход",
    }
    return mapping.get(kind, kind)


def _extract_queries(body: str) -> list[str]:
    queries: list[str] = []
    for match in QUERY_TEXT_RE.finditer(body):
        text = match.group(1).replace('""', '"').strip()
        if text:
            queries.append(text[:2000])
    return queries


def _registers_from_body(body: str) -> list[str]:
    found: set[str] = set()
    for match in MOVEMENT_ADD_RE.finditer(body):
        found.add(f"AccumulationRegister.{match.group(1)}")
    for match in REGISTER_QUERY_RE.finditer(body):
        found.add(f"AccumulationRegister.{match.group(1)}")
    return sorted(found)


def analyze_bsl_module(module_path: str) -> dict[str, Any]:
    """Возвращает движения, обработчики и запросы из BSL-модуля."""
    procedures = extract_bsl_procedures(module_path)
    movements: list[dict[str, Any]] = []
    handlers: list[dict[str, Any]] = []
    seen_movements: set[tuple[str, str, str]] = set()

    for proc in procedures:
        is_event = proc.name in EVENT_HANDLERS
        registers = _registers_from_body(proc.body)
        queries = _extract_queries(proc.body)

        if is_event or registers or queries:
            handlers.append({
                "name": proc.name,
                "module_path": module_path,
                "line_from": proc.start_line,
                "line_to": proc.end_line,
                "code": proc.body[:4000],
                "queries": queries,
                "registers_touched": registers,
            })

        for register_match in MOVEMENT_ADD_RE.finditer(proc.body):
            register_name = register_match.group(1)
            tail = proc.body[register_match.end() : register_match.end() + 400]
            kind_match = MOVEMENT_KIND_RE.search(tail)
            movement_kind = _movement_kind_ru(kind_match.group(1)) if kind_match else ""
            key = (register_name, movement_kind, proc.name)
            if key in seen_movements:
                continue
            seen_movements.add(key)
            movements.append({
                "register_type": "AccumulationRegister",
                "register_name": register_name,
                "movement_kind": movement_kind,
                "formed_in_code": True,
                "handler": proc.name,
            })

    return {
        "module_path": module_path,
        "movements": movements,
        "handlers": handlers,
        "procedure_count": len(procedures),
    }
