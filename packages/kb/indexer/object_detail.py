"""Детализированные ответы get_object по уровню detail."""

from __future__ import annotations

import re
from typing import Any

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.kb_index import get_object_from_index
from packages.kb.indexer.object_modules import list_object_modules
from packages.kb.indexer.store import get_by_metadata


def _fetch_metadata_card(config: ProfileConfig, object_type: str, object_name: str) -> tuple[str, dict[str, Any]]:
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
        return "", {}
    return docs[0], (metas[0] if metas else {})


def _format_brief(obj: dict[str, Any], card_text: str) -> str:
    lines = [
        f"## {obj.get('object_type')}.{obj.get('object_name')}",
        f"- Синоним: {obj.get('synonym') or '—'}",
        f"- Путь: {obj.get('path')}",
    ]
    if obj.get("subsystems"):
        lines.append(f"- Подсистемы: {', '.join(obj['subsystems'])}")
    if obj.get("attributes"):
        lines.append("\n### Реквизиты")
        for attr in obj["attributes"][:20]:
            syn = f" ({attr['synonym']})" if attr.get("synonym") else ""
            lines.append(f"- {attr['name']}: {attr.get('type', '?')}{syn}")
    if obj.get("tabular_sections"):
        lines.append("\n### Табличные части")
        for ts in obj["tabular_sections"]:
            cols = ", ".join(
                f"{a['name']}: {a.get('type', '?')}" for a in ts.get("attributes", [])
            )
            lines.append(f"- {ts['name']}: {cols}")
    if not obj.get("attributes") and not obj.get("tabular_sections") and card_text:
        body = card_text.split("---", 1)[-1].strip()
        if body:
            lines.append("")
            lines.append(body[:1500])
    return "\n".join(lines)


def _format_structure(obj: dict[str, Any]) -> str:
    lines = [
        f"## Структура: {obj.get('object_type')}.{obj.get('object_name')}",
        f"- Синоним: {obj.get('synonym') or '—'}",
        f"- Путь: {obj.get('path')}",
    ]
    if obj.get("posting"):
        lines.append(f"- Проведение: {obj['posting']}")
    if obj.get("real_time_posting"):
        lines.append(f"- Оперативное проведение: {obj['real_time_posting']}")
    if obj.get("register_type"):
        lines.append(f"- Тип регистра: {obj['register_type']}")
    if obj.get("register_records"):
        lines.append("\n### RegisterRecords")
        for rec in obj["register_records"]:
            lines.append(f"- {rec}")
    if obj.get("attributes"):
        lines.append("\n### Реквизиты")
        for attr in obj["attributes"]:
            syn = f" ({attr['synonym']})" if attr.get("synonym") else ""
            lines.append(f"- {attr['name']}: {attr.get('type', '?')}{syn}")
    if obj.get("tabular_sections"):
        lines.append("\n### Табличные части")
        for ts in obj["tabular_sections"]:
            lines.append(f"\n**{ts['name']}**")
            for attr in ts.get("attributes", []):
                lines.append(f"  - {attr['name']}: {attr.get('type', '?')}")
    if obj.get("dimensions"):
        lines.append("\n### Измерения")
        for dim in obj["dimensions"]:
            syn = f" ({dim['synonym']})" if dim.get("synonym") else ""
            lines.append(f"- {dim['name']}: {dim.get('type', '?')}{syn}")
    if obj.get("resources"):
        lines.append("\n### Ресурсы")
        for res in obj["resources"]:
            syn = f" ({res['synonym']})" if res.get("synonym") else ""
            lines.append(f"- {res['name']}: {res.get('type', '?')}{syn}")
    return "\n".join(lines)


def _format_movements(obj: dict[str, Any]) -> str:
    movements = obj.get("movements") or []
    title = f"{obj.get('object_type')}.{obj.get('object_name')}"
    if not movements:
        records = obj.get("register_records") or []
        if records:
            lines = [f"## Движения: {title}", ""]
            for rec in records:
                lines.append(f"- {rec} (только RegisterRecords в метаданных)")
            return "\n".join(lines)
        return f"У {title} нет движений по регистрам."

    lines = [f"## Движения: {title}", f"Двигает {len(movements)} регистр(ов):\n"]
    for mov in movements:
        rtype = mov.get("register_type", "AccumulationRegister")
        rname = mov.get("register_name", "?")
        rsyn = mov.get("register_synonym", "")
        header = f"### {rtype}.{rname}"
        if rsyn:
            header += f" ({rsyn})"
        lines.append(header)
        if mov.get("movement_kind"):
            lines.append(f"- Вид движения: {mov['movement_kind']}")
        if mov.get("dimensions"):
            lines.append(f"- Измерения: {', '.join(mov['dimensions'])}")
        if mov.get("resources"):
            lines.append(f"- Ресурсы: {', '.join(mov['resources'])}")
        flags = []
        if mov.get("declared_in_metadata"):
            flags.append("метаданные")
        if mov.get("formed_in_code"):
            flags.append("код")
        if flags:
            lines.append(f"- Источник: {', '.join(flags)}")
        if mov.get("handler"):
            lines.append(f"- Обработчик: {mov['handler']}")
        lines.append("")
    return "\n".join(lines)


_POSTING_EVENTS = frozenset({
    "ОбработкаПроведения",
    "ОбработкаУдаленияПроведения",
})
_PROC_CALL_RE = re.compile(
    r"(?<![\wА-Яа-яЁё])([\wА-Яа-яЁё][\wА-Яа-яЁё0-9]*)\s*\(",
    re.UNICODE,
)
def _logic_hints(related: dict[str, Any]) -> list[str]:
    hints: list[str] = []
    code = related.get("code", "")
    if "FIFO" in code.upper():
        hints.append("списание по FIFO")
    for query in related.get("queries", []):
        upper = query.upper()
        if "ОСТАТКИНОМЕНКЛАТУРЫ" in upper and ".ОСТАТКИ" in upper:
            hints.append("запрос к РегистрНакопления.ОстаткиНоменклатуры.Остатки")
        if "УПОРЯДОЧИТЬ ПО" in upper and "списание по FIFO" not in hints:
            hints.append("упорядочивание партий (FIFO)")
    return hints


def _related_handlers(handler: dict[str, Any], all_handlers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_name = {h["name"]: h for h in all_handlers}
    called: set[str] = set()
    for match in _PROC_CALL_RE.finditer(handler.get("code", "")):
        name = match.group(1)
        if name in by_name and name != handler.get("name"):
            called.add(name)
    return [by_name[name] for name in sorted(called)]


def _format_posting(obj: dict[str, Any]) -> str:
    handlers = obj.get("posting_handlers") or []
    title = f"{obj.get('object_type')}.{obj.get('object_name')}"
    if not handlers:
        return f"Обработчики проведения для {title} не найдены в индексе."

    event_handlers = [h for h in handlers if h.get("name") in _POSTING_EVENTS]
    display = event_handlers or handlers

    lines = [f"## Проведение: {title}\n"]
    for handler in display:
        lines.append(f"### {handler.get('name')}")
        lines.append(f"- Модуль: `{handler.get('module_path')}`")
        lines.append(f"- Строки: {handler.get('line_from')}–{handler.get('line_to')}")
        if handler.get("registers_touched"):
            lines.append(f"- Регистры в коде: {', '.join(handler['registers_touched'])}")
        if handler.get("queries"):
            lines.append("- Запросы:")
            for q in handler["queries"][:3]:
                preview = q.replace("\n", " ")[:300]
                lines.append(f"  ```\n  {preview}\n  ```")
        code = handler.get("code", "")
        if code:
            lines.append(f"```bsl\n{code[:2500]}\n```")
        for related in _related_handlers(handler, handlers):
            lines.append(f"\n#### Связанная процедура: {related.get('name')}")
            lines.append(f"- Строки: {related.get('line_from')}–{related.get('line_to')}")
            for hint in _logic_hints(related):
                lines.append(f"- Логика: {hint}")
            if related.get("registers_touched"):
                lines.append(f"- Регистры: {', '.join(related['registers_touched'])}")
            if related.get("queries"):
                lines.append("- Запросы:")
                for q in related["queries"][:2]:
                    preview = q.replace("\n", " ")[:400]
                    lines.append(f"  ```\n  {preview}\n  ```")
        lines.append("")
    return "\n".join(lines)


def _format_modules(config: ProfileConfig, object_type: str, object_name: str, obj: dict[str, Any]) -> str:
    modules = obj.get("modules")
    if modules is None:
        try:
            modules = list_object_modules(config, object_type, object_name)
        except Exception:
            modules = []
    if not modules:
        return ""
    lines = ["\n### Модули объекта"]
    for mod in modules:
        rel = mod.get("relative_path") or mod.get("path", "?")
        lines.append(f"- **{mod.get('name', '?')}** ({mod.get('kind', '')}): `{rel}`")
    return "\n".join(lines)


def get_object_detail(
    config: ProfileConfig,
    object_type: str,
    object_name: str,
    detail: str = "brief",
) -> str:
    detail = (detail or "brief").lower()
    obj = get_object_from_index(config, object_type, object_name)
    card_text, _meta = _fetch_metadata_card(config, object_type, object_name)

    if obj is None:
        if not card_text:
            return f"Объект {object_type}.{object_name} не найден."
        if detail == "brief":
            return card_text
        return f"Объект {object_type}.{object_name} найден в Chroma, но нет в KB-индексе. Переиндексируйте профиль."

    if detail == "brief":
        return _format_brief(obj, card_text)
    if detail == "structure":
        return _format_structure(obj)
    if detail == "movements":
        return _format_movements(obj)
    if detail == "posting":
        return _format_posting(obj)
    if detail == "full":
        parts = [
            _format_structure(obj),
            "",
            _format_movements(obj),
            "",
            _format_posting(obj),
            _format_modules(config, object_type, object_name, obj),
        ]
        return "\n".join(p for p in parts if p)

    return f"Неизвестный detail={detail!r}. Допустимо: brief, structure, movements, posting, full."
