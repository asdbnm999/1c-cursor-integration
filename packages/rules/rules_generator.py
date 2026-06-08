"""Генерация markdown-файла правил по шаблону и данным анализа выгрузки."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from .advanced_rules import ADVANCED_EVENT_LOG_KEYS, ADVANCED_GENERIC, ADVANCED_RULE_SPECS
from .mcp_rules import build_mcp_rules_section
from .event_log_rules_generator import event_log_rules_path, generate_event_log_rules_markdown
from .export_analyzer import ExportAnalysis
from .field_choices import VCS_NONE
from .field_choices import AI_PATCH_WRAP_DISABLED, AI_PATCH_WRAP_ENABLED

MANUAL_PLACEHOLDER = "[ЗАПОЛНИТЬ]"
OPTIONAL_NOTE = "при необходимости уточните в файле или в дополнительных правилах парсера"


def _script_variant_label(variant: str | None) -> str:
    if variant == "Russian":
        return "русский"
    if variant == "English":
        return "английский"
    return MANUAL_PLACEHOLDER


def _run_mode_label(mode: str | None) -> str:
    if mode == "ManagedApplication":
        return "управляемое приложение"
    if mode == "OrdinaryApplication":
        return "обычное приложение"
    return mode or "—"


def _ai_bsl_wrap_block(marker: str) -> str:
    """Правило обрамления доработок нейросети в модулях .bsl."""
    return f"""
### Обрамление доработок в коде (.bsl)

> **Обязательно** при каждом изменении или добавлении кода нейросетью в файлах `.bsl`.

Каждый непрерывный блок доработки оборачивать парой комментариев. Метка в квадратных скобках: **`{marker}`** (задана в парсере правил).

**Начало блока** (первая строка перед доработкой):

```bsl
// [{marker}] Начало <ТекущаяДатаВремя> {{{{
```

**Конец блока** (первая строка после доработки):

```bsl
// }}}}[{marker}] Конец
```

- **`<ТекущаяДатаВремя>`** — фактические дата и время внесения доработки в формате `dd.MM.yyyy HH:mm:ss` (локальное время сеанса правки). Для каждого нового блока — своё значение.
- Между строками «Начало» и «Конец» — только код, относящийся к этой доработке.
- Если в одном файле несколько отдельных доработок — **отдельная пара** «Начало/Конец» на каждую.
- Не оборачивать типовой код без изменений; не разрывать одну логическую доработку несколькими парами без необходимости.
- Правило не отменяет комментарии внутри кода по стандартам проекта.
"""


def _ai_bsl_no_wrap_block() -> str:
    """Правило без обрамления (небезопасный режим)."""
    return """
### Обрамление доработок в коде (.bsl)

> ⚠️ **Небезопасный режим** (явно выбрано в парсере правил): доработки **не** оборачиваются маркерами «Начало/Конец».

- Нейросеть **не добавляет** комментарии вида `// [Текст] Начало <дата> {{` и `// }}[Текст] Конец` вокруг своего кода в `.bsl`.
- **Риски:** труднее отличить AI-код от ручного при слиянии и ревью; сложнее точечный откат; выше риск пропустить чужую правку в типовом модуле.
- Если задача не требует отключения маркеров — пересоздайте файл правил с режимом «Оборачивать доработки комментариями».
"""


def _ai_commenting_block(ov: dict[str, str]) -> str:
    """Раздел правил пояснения решений нейросетью."""
    wrap_mode = ov.get("ai_patch_wrap", AI_PATCH_WRAP_ENABLED)
    marker = ov.get("ai_patch_marker", MANUAL_PLACEHOLDER)
    when = ov.get("ai_explain_when", MANUAL_PLACEHOLDER)
    language = ov.get("ai_explain_language", MANUAL_PLACEHOLDER)
    detail = ov.get("ai_explain_detail", MANUAL_PLACEHOLDER)
    include_raw = ov.get("ai_explain_include")
    if include_raw and include_raw.startswith("- "):
        include = include_raw.replace("\n", "\n  ")
    else:
        include = include_raw or MANUAL_PLACEHOLDER
    fmt = ov.get("ai_explain_format", MANUAL_PLACEHOLDER)
    extra_raw = ov.get("ai_explain_extra")
    custom = ov.get("ai_explain_custom")

    if include_raw and include_raw.startswith("- "):
        include_line = f"- **Что обязательно включать в пояснение:**\n  {include}"
    else:
        include_line = f"- **Что обязательно включать в пояснение:** {include}"

    if extra_raw and extra_raw.startswith("- "):
        extra_fmt = extra_raw.replace("\n", "\n  ")
        extra_line = f"- **Дополнительные правила комментирования:**\n  {extra_fmt}"
    elif extra_raw:
        extra_line = f"- **Дополнительные правила комментирования:** {extra_raw}"
    else:
        extra_line = ""

    lines = [
        "",
        "## Комментирование решений AI",
        "",
        "> Как нейросеть должна **пояснять свои решения** пользователю: когда, на каком языке, "
        "с какой детальностью и в каком формате. Не путать с комментариями в коде BSL.",
        "",
        "### Когда и как пояснять",
        "",
        f"- **Когда пояснять:** {when}",
        f"- **Язык пояснений:** {language}",
        f"- **Детальность:** {detail}",
        include_line,
        f"- **Формат пояснения:** {fmt}",
    ]
    if extra_line:
        lines.append(extra_line)

    lines.append(f"- **Обрамление доработок в .bsl:** {wrap_mode}")

    if wrap_mode == AI_PATCH_WRAP_DISABLED:
        lines.append(_ai_bsl_no_wrap_block())
    elif marker and marker != MANUAL_PLACEHOLDER:
        lines.append(_ai_bsl_wrap_block(marker))
    else:
        lines.extend(
            [
                "",
                "### Обрамление доработок в коде (.bsl)",
                "",
                f"- Метка `[Текст]` и правило обрамления: `{MANUAL_PLACEHOLDER}` (задаётся в парсере: «Метка [Текст] в обрамлении доработок»)",
            ]
        )

    lines.extend(
        [
            "",
            "### Структура пояснения (рекомендуемый шаблон)",
            "",
            "1. **Сделано** — что изменено и зачем (1–3 предложения).",
            "2. **Файлы** — перечень затронутых путей в выгрузке (XML/BSL).",
            "3. **Решения** — почему выбран подход; отвергнутые альтернативы (если были).",
            "4. **Риски и проверки** — что может сломаться, что проверить вручную.",
            "5. **Не входило в задачу** — что сознательно не делалось.",
            "",
            "### Запреты при пояснении",
            "",
            "- Не выдумывать выполненные действия и не описывать несуществующие файлы.",
            "- Не раскрывать содержимое секретов (.env, пароли, токены).",
            "- Не заменять пояснением обязательные правила из раздела «Обязательные правила».",
        ]
    )

    if custom:
        lines.extend(
            [
                "",
                "### Свои правила комментирования",
                "",
                custom,
            ]
        )
    elif when == MANUAL_PLACEHOLDER and language == MANUAL_PLACEHOLDER:
        lines.extend(
            [
                "",
                f"### Свои правила комментирования",
                "",
                f"- `{MANUAL_PLACEHOLDER}`",
            ]
        )

    lines.append("")
    return "\n".join(lines)


def _workflow_block(apply_via: str) -> str:
    apply_line = apply_via if apply_via != MANUAL_PLACEHOLDER else MANUAL_PLACEHOLDER
    return f"""
### Рабочий процесс (кто что делает)

> Базовая модель для этого проекта. AI **не** открывает конфигуратор и EDT.

1. **Пользователь** выгружает конфигурацию в каталог XML (конфигуратор → «Выгрузить в файлы»).
2. **AI (асистент)** вносит доработки **напрямую в файлы выгрузки** на диске: `.xml`, `.bsl`, каталоги метаданных.
3. **Пользователь** переносит результат в 1С: загрузка/сравнение в конфигураторе и/или работа с проектом в EDT — по выбранному способу ниже.
4. Пользователь **не обязан** дублировать вручную то, что AI уже изменил в файлах, если не оговорено иное.

- **Куда переносите правки AI:** {apply_line}
- **Редактор для общения с AI:** Cursor (или аналог) — только чат и просмотр диффа, не замена п.2.
- **Откуда выгрузили** — см. «Формат выгрузки» выше (это источник выгрузки, не место правок AI).
"""


def _advanced_line(label: str, key: str, ov: dict[str, str]) -> str:
    val = ov.get(key)
    if val:
        return f"- **{label}:** {val}"
    generic = ADVANCED_GENERIC.get(key)
    if generic:
        return f"- {generic}"
    return f"- **{label}:** {OPTIONAL_NOTE}"


def _advanced_rules_sections(
    ov: dict[str, str],
    *,
    encoding_hint: str = "",
    event_log_filename: str | None = None,
) -> str:
    by_section: dict[str, list[str]] = {}
    for spec in ADVANCED_RULE_SPECS:
        if spec["key"] in ADVANCED_EVENT_LOG_KEYS:
            continue
        sec = spec["section"]
        by_section.setdefault(sec, []).append(_advanced_line(spec["label"], spec["key"], ov))

    parts = [
        "",
        "## Работа с XML-выгрузкой",
        "",
        "> Универсальные правила для любой выгрузки этого проекта. Конкретные значения ниже "
        "задаются в парсере (кнопка «Дополнительные правила»); незаполненные пункты "
        "остаются общими формулировками.",
        "",
        "### Что можно и нельзя менять",
        "",
        f"- **Какие типы объектов редактировать:** {OPTIONAL_NOTE}",
        f"- **Типовые объекты, подписи, UUID:** {OPTIONAL_NOTE}",
        "",
        "### Правила редактирования XML",
        "",
    ]
    for line in by_section.get("XML-выгрузка", []):
        parts.append(line)
    edt_lines = by_section.get("EDT-проект", [])
    if edt_lines:
        parts.extend(["", "### EDT-проект", ""])
        parts.extend(edt_lines)
    parts.extend(
        [
            "",
            "### Модули (.bsl)",
            "",
        ]
    )
    for line in by_section.get("Модули .bsl", []):
        parts.append(line)
    enc = encoding_hint or OPTIONAL_NOTE
    parts.append(f"- **Кодировка модулей:** {enc}")

    parts.extend(["", "## Архитектурные правила", ""])
    for line in by_section.get("Архитектура", []):
        parts.append(line)
    parts.extend(
        [
            f"- **Разделение по слоям:** {OPTIONAL_NOTE}",
            f"- **Именование модулей:** {OPTIONAL_NOTE}",
            f"- **Имя расширения:** {OPTIONAL_NOTE}",
            f"- **Запрещённые вызовы:** {OPTIONAL_NOTE}",
        ]
    )

    parts.extend(["", "## Транзакции, блокировки, ошибки", ""])
    for line in by_section.get("Транзакции и ошибки", []):
        parts.append(line)
    parts.append(f"- **Гранулярность транзакций:** {OPTIONAL_NOTE}")
    log_ref = (
        f"отдельный файл `{event_log_filename}` (генерируется вместе с этим)"
        if event_log_filename
        else OPTIONAL_NOTE
    )
    parts.append(f"- **Журнал регистрации:** {log_ref}")

    parts.extend(["", "## Запросы и производительность", ""])
    for line in by_section.get("Запросы", []):
        parts.append(line)
    parts.append(f"- **Ограничения по объёму данных:** {OPTIONAL_NOTE}")

    parts.extend(["", "## Интеграции и внешние API", ""])
    for line in by_section.get("Интеграции", []):
        parts.append(line)
    parts.append(f"- **Таймауты и повторы:** {OPTIONAL_NOTE}")
    parts.append(f"- **Формат обмена:** {OPTIONAL_NOTE}")

    parts.extend(["", "## Запреты", ""])
    for line in by_section.get("Запреты", []):
        parts.append(line)
    parts.append(f"- **Прочие ограничения:** {OPTIONAL_NOTE}")

    return "\n".join(parts) + "\n"


def _metadata_inventory_block(analysis: ExportAnalysis) -> str:
    if not analysis.metadata_counts:
        return "_В выгрузке не обнаружены каталоги объектов метаданных верхнего уровня._\n"
    lines = [
        "",
        "## Состав конфигурации (из выгрузки)",
        "",
        "> Раздел сформирован автоматически. Используйте как справочник по объектам метаданных.",
        "",
        "| Тип | Кол-во | Объекты |",
        "|-----|--------|---------|",
    ]
    for label in sorted(analysis.metadata_counts.keys()):
        count = analysis.metadata_counts[label]
        names = analysis.metadata_objects.get(label, [])
        names_str = ", ".join(names[:12])
        if len(names) > 12:
            names_str += f" … (+{len(names) - 12})"
        lines.append(f"| {label} | {count} | {names_str} |")
    lines.append("")
    return "\n".join(lines)


def generate_rules_markdown(
    analysis: ExportAnalysis,
    *,
    output_path: Path | None = None,
    manual_overrides: dict[str, str] | None = None,
    event_log_filename: str | None = None,
    mcp_rules: dict | None = None,
) -> str:
    """
    Собирает текст markdown по шаблону правил разработки.

    manual_overrides: опциональные значения для полей, которые иначе остаются [ЗАПОЛНИТЬ].
    Ключи: solution_type, apply_changes_via, vcs, ai_explain_* и т.д.
    """
    ov = manual_overrides or {}
    export_path = str(analysis.export_path)
    config_name = analysis.display_config_name
    platform = analysis.platform_hint or MANUAL_PLACEHOLDER
    cfg_version = analysis.config_version or MANUAL_PLACEHOLDER
    solution_type = ov.get("solution_type", MANUAL_PLACEHOLDER)
    export_fmt = analysis.export_format_label or MANUAL_PLACEHOLDER
    encoding = analysis.xml_encoding or MANUAL_PLACEHOLDER
    from .form_api import apply_changes_via_for_analysis

    apply_via = ov.get("apply_changes_via") or apply_changes_via_for_analysis(analysis) or MANUAL_PLACEHOLDER
    vcs = ov.get("vcs", MANUAL_PLACEHOLDER)
    branch = ov.get("default_branch", MANUAL_PLACEHOLDER)
    branch_line = ""
    if vcs == VCS_NONE:
        branch_line = "- **Ветка по умолчанию:** не используется (выбрано «Без СКВ»)\n"
    else:
        branch_line = f"- **Ветка по умолчанию:** {branch}\n"

    prefix = analysis.name_prefix or ov.get("dev_prefix") or MANUAL_PLACEHOLDER
    if prefix == "":
        prefix = MANUAL_PLACEHOLDER

    lang_names = _script_variant_label(analysis.script_variant)

    vendor_line = ""
    if analysis.config_vendor:
        vendor_line = f"\n- **Поставщик (из выгрузки):** {analysis.config_vendor}"
    comment_line = ""
    if analysis.config_comment:
        comment_line = f"\n- **Комментарий конфигурации:** {analysis.config_comment}"

    platform_line = platform if platform != MANUAL_PLACEHOLDER else "уточните по актуальной выгрузке"
    cfg_line = cfg_version if cfg_version != MANUAL_PLACEHOLDER else "—"
    solution_line = solution_type if solution_type != MANUAL_PLACEHOLDER else OPTIONAL_NOTE
    vcs_line = vcs if vcs != MANUAL_PLACEHOLDER else OPTIONAL_NOTE
    encoding_line = encoding if encoding != MANUAL_PLACEHOLDER else "UTF-8, если иное не задано в проекте"

    today = date.today().isoformat()

    body = f"""# Правила разработки 1С в XML-выгрузке

> **Многоразовый** файл настроек для AI-асистента. Рассчитан на разные версии выгрузки одного проекта.
> В начале задачи прикладывайте этот файл или указывайте путь к нему.
>
> _Сгенерировано парсером выгрузки 1С. Снимок контекста ниже — на момент генерации; при смене выгрузки пересоздайте файл или обновите раздел «Контекст»._

---

## Как использовать

1. Основные параметры задайте в форме парсера (пути, СКВ, комментирование AI, пояснения).
2. Пункты «да / нет» и варианты — в **«Дополнительные правила»** (необязательно); незаполненное остаётся общей формулировкой.
3. **Журнал регистрации** — в отдельном `.md` рядом с этим файлом; прикладывайте оба при работе с ошибками и фоном.
4. Дополняйте файл своими правилами в конце разделов; устаревшее помечайте `(устарело)`.
5. AI правит **файлы выгрузки**; вы переносите результат в 1С — см. «Рабочий процесс».

---

## Контекст проекта (снимок при генерации)

### Конфигурация

- **Имя конфигурации:** {config_name}
- **Ориентир версии платформы:** {platform_line}
- **Версия конфигурации (на момент генерации):** {cfg_line}
- **Тип решения:** {solution_line}
- **Режим запуска:** {_run_mode_label(analysis.default_run_mode)}
- **Формат выгрузки:** {export_fmt}{vendor_line}{comment_line}

### Путь к XML-выгрузке

- **Пример корня (при генерации):** `{export_path}`
- **Кодировка (типично для проекта):** {encoding_line}

### Среда и перенос правок

- **Система контроля версий:** {vcs_line}
{branch_line}"""
    body += _workflow_block(apply_via)
    body += _ai_commenting_block(ov)
    body += f"""
---

## Обязательные правила (всегда соблюдать)

> Правила с наивысшим приоритетом. AI не должна их нарушать.

- **Редактировать файлы выгрузки напрямую** (XML/BSL в каталоге выгрузки), а не «описывать правки» без изменения файлов.
- **Не требовать** от пользователя вручную повторять правки, которые AI может внести в выгрузку.
- **Не открывать и не управлять** конфигуратором 1С и EDT — только подсказать пользователю шаги загрузки/сравнения, если нужно.
- В конце задачи **кратко указать**, какие файлы изменены и как пользователю применить их в 1С ({apply_via if apply_via != MANUAL_PLACEHOLDER else "конфигуратор / EDT"}).

---

## Стиль кода и соглашения

> Не привязан к числу модулей в одной выгрузке — действует для любой версии каталога.

### Именование

- **Префикс доработок:** {prefix}
- **Язык имён объектов:** {lang_names}
- **Стиль процедур и функций:** {OPTIONAL_NOTE}

### Структура модулей

- **Области `#Область` / `#КонецОбласти`:** как принято в вашем проекте
- **Порядок областей:** {OPTIONAL_NOTE}
- **Комментарии к экспортным методам:** {OPTIONAL_NOTE}

### Форматирование

- **Отступы (таб / пробелы):** единообразно в рамках проекта
- **Длина строки:** {OPTIONAL_NOTE}
- **Пустая строка между процедурами:** {OPTIONAL_NOTE}
"""
    body += _advanced_rules_sections(
        ov,
        encoding_hint=encoding_line,
        event_log_filename=event_log_filename,
    )
    if mcp_rules:
        body += build_mcp_rules_section(mcp_rules)
    body += f"""
---

## Git и коммиты

> Заполняйте при работе через Git.

- **Формат сообщений коммитов:** {OPTIONAL_NOTE}
- **Что не коммитить:** {OPTIONAL_NOTE}
- **Создавать коммиты автоматически:** только по запросу пользователя

---

## Чеклист перед сдачей задачи

AI должна проверить перед завершением:

- [ ] Изменения только в нужных файлах XML/BSL
- [ ] Не сломаны UUID и ссылки между объектами
- [ ] Соблюдены префиксы и соглашения именования
- [ ] Нет лишних `Сообщить()` / отладочного кода
- [ ] Добавлена/обновлена документация к экспортным методам (если требуется)
- [ ] В ответе есть пояснение решений AI по разделу «Комментирование решений AI»

---

## Примеры (эталонный код)

> Вставляйте фрагменты «как надо писать» — AI будет ориентироваться на них.

```bsl
// Пример оформления процедуры — {OPTIONAL_NOTE}
```

---

## История изменений правил

| Дата | Автор | Что изменено |
|------|-------|--------------|
| {today} | парсер выгрузки 1С | Создан или обновлён файл правил |

---

## Свободные заметки

> Любые дополнительные указания, контекст, ссылки на документацию.

- {OPTIONAL_NOTE}
"""

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(body, encoding="utf-8")

    return body


def default_rules_basename(analysis: ExportAnalysis) -> str:
    name = (analysis.config_name or "").strip()
    suffix = f"-{name}" if name else ""
    return f"1С-правила-разработки{suffix}"


def generate_rules_bundle(
    analysis: ExportAnalysis,
    *,
    output_path: Path,
    manual_overrides: dict[str, str] | None = None,
    mcp_rules: dict | None = None,
) -> tuple[str, str, Path, Path]:
    """Основной файл правил и отдельный файл журнала регистрации."""
    main_path = Path(output_path)
    log_path = event_log_rules_path(main_path)
    ov = manual_overrides or {}

    main_md = generate_rules_markdown(
        analysis,
        output_path=main_path,
        manual_overrides=ov,
        event_log_filename=log_path.name,
        mcp_rules=mcp_rules,
    )
    log_md = generate_event_log_rules_markdown(
        analysis,
        output_path=log_path,
        manual_overrides=ov,
        main_rules_filename=main_path.name,
    )
    return main_md, log_md, main_path, log_path
