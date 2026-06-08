"""Перечисления значений для полей формы (кроме пути к выгрузке и файла результата)."""

from __future__ import annotations

# Специальные пункты combobox (не попадают в markdown как есть)
NOT_SET_LABEL = "— не задано —"
MANUAL_INPUT_LABEL = "Ручной ввод"

SOLUTION_TYPES = ("типовая", "доработанная", "самописная")

# Куда пользователь переносит правки AI (сами файлы правит AI в каталоге выгрузки)
APPLY_CHANGES_VIA_OPTIONS = (
    "Конфигуратор 1С (загрузка/сравнение выгрузки)",
    "EDT",
    "Конфигуратор и EDT",
)

VCS_NONE = "Без СКВ"

VCS_OPTIONS = ("Git", "Хранилище 1С", "SVN", VCS_NONE)

BRANCH_OPTIONS = ("main", "master", "develop", "staging", "release")

PREFIX_OPTIONS = ("фд_", "хн_", "нфо_", "бит_")

# Обрамление доработок в .bsl
AI_PATCH_WRAP_ENABLED = "Оборачивать доработки комментариями (рекомендуется)"
AI_PATCH_WRAP_DISABLED = "Не оборачивать комментариями"

AI_PATCH_WRAP_OPTIONS = (AI_PATCH_WRAP_ENABLED, AI_PATCH_WRAP_DISABLED)

AI_PATCH_WRAP_WARNING = (
    "Небезопасно: без маркеров сложнее ревью, откат и поиск AI-правок в типовом коде. "
    "Рекомендуется включить обрамление."
)

AI_PATCH_MARKER = ("AI", "Доработка", "Нейросеть", "Cursor")
AI_PATCH_MARKER_DEFAULT = "Cursor"

# --- Блок «Комментирование» (маркеры в .bsl, когда и доп. правила) ---

AI_EXPLAIN_WHEN = (
    "Всегда в конце ответа — кратко по сделанному",
    "Только нетривиальные решения и риски",
    "Только по запросу пользователя",
    "Не пояснять — только код и факты",
)

AI_EXPLAIN_EXTRA = (
    "Не пересказывать дифф в пояснении",
    "Перечислить, что сознательно не трогали",
    "После правок — план ручной проверки",
    "Спорное решение — по файлу правил",
)

AI_EXPLAIN_CUSTOM_ONLY_FIELDS = "Использовать только поля выше"

# --- Блок «Пояснения» (язык, содержание, формат ответа) ---

AI_EXPLAIN_LANGUAGE = (
    "Русский",
    "Английский",
    "Язык запроса пользователя",
)
AI_EXPLAIN_LANGUAGE_DEFAULT = "Русский"

AI_EXPLAIN_DETAIL = (
    "Кратко — 3–7 пунктов",
    "Средне — что, почему, какие файлы",
    "Подробно — контекст, альтернативы, ограничения",
)

AI_EXPLAIN_INCLUDE = (
    "Список изменённых файлов и суть правок",
    "Обоснование выбора подхода",
    "Риски, побочные эффекты и что проверить вручную",
    "Ссылки на объекты метаданных 1С (имена, не UUID)",
)
AI_EXPLAIN_INCLUDE_DEFAULT = (
    AI_EXPLAIN_INCLUDE[0],
    AI_EXPLAIN_INCLUDE[1],
    AI_EXPLAIN_INCLUDE[2],
)

AI_EXPLAIN_FORMAT = (
    "Markdown — заголовки и маркированные списки",
    "Нумерованный отчёт — шаги 1, 2, 3…",
    "Таблица — файл и суть изменения",
)
AI_EXPLAIN_FORMAT_DEFAULT = AI_EXPLAIN_FORMAT[2]

FIELD_SPECS: dict[str, dict] = {
    "solution_type": {
        "label": "Тип решения:",
        "options": SOLUTION_TYPES,
        "allow_not_set": True,
    },
    "apply_changes_via": {
        "label": "Куда вы переносите правки AI после доработки:",
        "options": APPLY_CHANGES_VIA_OPTIONS,
        "allow_not_set": True,
    },
    "vcs": {
        "label": "Система контроля версий:",
        "options": VCS_OPTIONS,
        "allow_not_set": True,
    },
    "default_branch": {
        "label": "Ветка по умолчанию:",
        "options": BRANCH_OPTIONS,
        "allow_not_set": True,
        "hide_when_vcs_is": VCS_NONE,
    },
    "dev_prefix": {
        "label": "Префикс доработок:",
        "options": PREFIX_OPTIONS,
        "allow_not_set": True,
    },
}

AI_COMMENT_FIELD_SPECS: dict[str, dict] = {
    "ai_patch_wrap": {
        "label": "Обрамление доработок в .bsl:",
        "options": AI_PATCH_WRAP_OPTIONS,
        "allow_not_set": False,
        "default": AI_PATCH_WRAP_ENABLED,
        "warning_for": {AI_PATCH_WRAP_DISABLED: AI_PATCH_WRAP_WARNING},
    },
    "ai_patch_marker": {
        "label": "Метка [Текст] в обрамлении доработок .bsl:",
        "options": AI_PATCH_MARKER,
        "allow_not_set": False,
        "default": AI_PATCH_MARKER_DEFAULT,
        "visible_when_wrap_enabled": True,
    },
    "ai_explain_when": {
        "label": "Когда пояснять решения:",
        "options": AI_EXPLAIN_WHEN,
        "allow_not_set": True,
    },
    "ai_explain_extra": {
        "label": "Дополнительные правила комментирования:",
        "options": AI_EXPLAIN_EXTRA,
        "field_type": "checkboxes",
        "allow_not_set": False,
        "allow_manual": False,
        "default_checked": (),
    },
    "ai_explain_custom": {
        "label": "Свои правила комментирования (полный текст):",
        "options": (AI_EXPLAIN_CUSTOM_ONLY_FIELDS,),
        "allow_not_set": False,
        "default": AI_EXPLAIN_CUSTOM_ONLY_FIELDS,
        "manual_multiline": True,
    },
}

AI_EXPLAIN_FIELD_SPECS: dict[str, dict] = {
    "ai_explain_language": {
        "label": "Язык пояснений:",
        "options": AI_EXPLAIN_LANGUAGE,
        "allow_not_set": True,
        "default": AI_EXPLAIN_LANGUAGE_DEFAULT,
    },
    "ai_explain_detail": {
        "label": "Детальность пояснений:",
        "options": AI_EXPLAIN_DETAIL,
        "allow_not_set": True,
    },
    "ai_explain_include": {
        "label": "Что обязательно включать в пояснение:",
        "options": AI_EXPLAIN_INCLUDE,
        "field_type": "checkboxes",
        "allow_not_set": False,
        "allow_manual": True,
        "default_checked": AI_EXPLAIN_INCLUDE_DEFAULT,
    },
    "ai_explain_format": {
        "label": "Формат пояснения:",
        "options": AI_EXPLAIN_FORMAT,
        "allow_not_set": True,
        "default": AI_EXPLAIN_FORMAT_DEFAULT,
    },
}

AI_FIELD_SPECS: dict[str, dict] = {**AI_COMMENT_FIELD_SPECS, **AI_EXPLAIN_FIELD_SPECS}

ALL_FIELD_SPECS: dict[str, dict] = {**FIELD_SPECS, **AI_FIELD_SPECS}


def combobox_values(options: tuple[str, ...], *, allow_not_set: bool = True) -> list[str]:
    items: list[str] = []
    if allow_not_set:
        items.append(NOT_SET_LABEL)
    items.extend(options)
    items.append(MANUAL_INPUT_LABEL)
    return items


def checkbox_values(
    options: tuple[str, ...],
    *,
    allow_not_set: bool = False,
    allow_manual: bool = True,
) -> list[str]:
    items = list(options)
    if allow_not_set:
        items.insert(0, NOT_SET_LABEL)
    if allow_manual:
        items.append(MANUAL_INPUT_LABEL)
    return items
