"""Точечное чтение BSL-модулей для get_module."""

from __future__ import annotations

from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.exceptions import SourceNotFoundError
from packages.kb.indexer.extract_bsl import extract_bsl_procedures

EVENT_HANDLERS = frozenset({
    "ОбработкаПроведения",
    "ОбработкаУдаленияПроведения",
    "ПередЗаписью",
    "ПриЗаписи",
    "ПередУдалением",
    "ОбработкаЗаполнения",
    "ОбработкаПроверкиЗаполнения",
})


def _resolve_module_path(config: ProfileConfig, module_path: str) -> Path:
    raw = Path(module_path)
    if raw.is_file():
        return raw.resolve()
    candidate = (config.source_base / module_path).resolve()
    if candidate.is_file():
        return candidate
    raise SourceNotFoundError("Модуль не найден", details=module_path)


def read_module(
    config: ProfileConfig,
    module_path: str,
    *,
    mode: str = "summary",
    name: str = "",
    line_from: int = 0,
    line_to: int = 0,
) -> str:
    path = _resolve_module_path(config, module_path)
    mode = (mode or "summary").lower()
    content = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = content.splitlines()
    rel = path
    try:
        rel = path.relative_to(config.source_base)
    except ValueError:
        pass

    if mode == "summary":
        procedures = extract_bsl_procedures(str(path))
        exports = [p for p in procedures if p.is_export]
        result = [
            f"## Модуль: {rel}",
            f"- Полный путь: `{path}`",
            f"- Строк: {len(lines)}",
            f"- Процедур/функций: {len(procedures)}",
            "",
        ]
        events = [p for p in procedures if p.name in EVENT_HANDLERS]
        if events:
            result.append("### Обработчики событий")
            for proc in events:
                result.append(f"- {proc.signature} (стр. {proc.start_line}–{proc.end_line})")
            result.append("")
        if exports:
            result.append("### Экспортные методы")
            for proc in exports:
                region = f" [{proc.region}]" if proc.region else ""
                result.append(f"- {proc.signature}{region} (стр. {proc.start_line}–{proc.end_line})")
        else:
            result.append("Экспортные методы не найдены.")
        regions = sorted({p.region for p in procedures if p.region})
        if regions:
            result.append("\n### Области")
            result.extend(f"- {r}" for r in regions)
        return "\n".join(result)

    if mode == "procedure":
        if not name:
            return "Укажите name — имя процедуры или функции."
        for proc in extract_bsl_procedures(str(path)):
            if proc.name.lower() == name.lower():
                return (
                    f"## {proc.signature}\n"
                    f"- Модуль: `{rel}`\n"
                    f"- Строки: {proc.start_line}–{proc.end_line}\n\n"
                    f"```bsl\n{proc.body}\n```"
                )
        return f"Процедура/функция «{name}» не найдена в `{rel}`."

    if mode == "event":
        if not name:
            return "Укажите name — имя обработчика события (например, ОбработкаПроведения)."
        for proc in extract_bsl_procedures(str(path)):
            if proc.name == name:
                return (
                    f"## Событие: {proc.name}\n"
                    f"- Модуль: `{rel}`\n"
                    f"- Строки: {proc.start_line}–{proc.end_line}\n\n"
                    f"```bsl\n{proc.body}\n```"
                )
        return f"Обработчик «{name}» не найден в `{rel}`."

    if mode == "fragment":
        if line_from <= 0 or line_to <= 0 or line_to < line_from:
            return "Для mode=fragment укажите line_from и line_to (номера строк, с 1)."
        start = max(1, line_from)
        end = min(len(lines), line_to)
        fragment = "\n".join(lines[start - 1 : end])
        numbered = "\n".join(
            f"{start + i:4d} | {line}" for i, line in enumerate(lines[start - 1 : end])
        )
        return (
            f"## Фрагмент: `{rel}` ({start}–{end})\n\n"
            f"```bsl\n{numbered}\n```"
        )

    return f"Неизвестный mode={mode!r}. Допустимо: summary, procedure, event, fragment."
