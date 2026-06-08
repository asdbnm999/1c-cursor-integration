"""API-слой: спецификация формы и сбор overrides для веб-интерфейса."""

from __future__ import annotations

from typing import Any

from .advanced_rules import (
    ADVANCED_SKIP_LABEL,
    advanced_modal_initial_defaults,
    advanced_to_overrides,
    recommended_advanced_defaults,
    serialize_advanced_specs,
)
from .export_analyzer import ExportAnalysis
from .field_choices import (
    AI_COMMENT_FIELD_SPECS,
    AI_EXPLAIN_CUSTOM_ONLY_FIELDS,
    AI_EXPLAIN_FIELD_SPECS,
    AI_FIELD_SPECS,
    AI_PATCH_WRAP_DISABLED,
    AI_PATCH_WRAP_ENABLED,
    FIELD_SPECS,
    MANUAL_INPUT_LABEL,
    NOT_SET_LABEL,
    PREFIX_OPTIONS,
    VCS_NONE,
    checkbox_values,
    combobox_values,
)

SKIP_VALUES = frozenset({NOT_SET_LABEL, AI_EXPLAIN_CUSTOM_ONLY_FIELDS})


def _serialize_spec(key: str, spec: dict) -> dict[str, Any]:
    raw_options = tuple(spec["options"])
    warning_for = spec.get("warning_for") or {}
    if spec.get("field_type") == "checkboxes":
        options = checkbox_values(
            raw_options,
            allow_not_set=spec.get("allow_not_set", False),
            allow_manual=spec.get("allow_manual", True),
        )
    else:
        options = combobox_values(raw_options, allow_not_set=spec.get("allow_not_set", True))
    return {
        "key": key,
        "label": spec["label"],
        "options": options,
        "default": spec.get("default"),
        "allow_not_set": spec.get("allow_not_set", True),
        "manual_multiline": spec.get("manual_multiline", False),
        "warning_for": dict(warning_for),
        "visible_when_wrap_enabled": spec.get("visible_when_wrap_enabled", False),
        "hide_when_vcs_is": spec.get("hide_when_vcs_is"),
        "field_type": spec.get("field_type", "select"),
        "default_checked": list(spec.get("default_checked") or ()),
    }


def get_form_schema() -> dict[str, Any]:
    return {
        "constants": {
            "not_set": NOT_SET_LABEL,
            "manual_input": MANUAL_INPUT_LABEL,
            "wrap_enabled": AI_PATCH_WRAP_ENABLED,
            "wrap_disabled": AI_PATCH_WRAP_DISABLED,
            "vcs_none": VCS_NONE,
            "advanced_skip": ADVANCED_SKIP_LABEL,
        },
        "general_fields": [
            _serialize_spec(k, s)
            for k, s in FIELD_SPECS.items()
            if k != "apply_changes_via"
        ],
        "ai_comment_fields": [
            _serialize_spec(k, s) for k, s in AI_COMMENT_FIELD_SPECS.items()
        ],
        "ai_explain_fields": [
            _serialize_spec(k, s) for k, s in AI_EXPLAIN_FIELD_SPECS.items()
        ],
        "ai_fields": [
            _serialize_spec(k, s) for k, s in AI_FIELD_SPECS.items()
        ],
        "advanced_fields": serialize_advanced_specs(),
        "advanced_initial_defaults": advanced_modal_initial_defaults(),
        "advanced_recommended_defaults": recommended_advanced_defaults(),
    }


def resolve_field_value(choice: str, custom: str = "") -> str | None:
    choice = (choice or "").strip()
    custom = (custom or "").strip()
    if choice in SKIP_VALUES or not choice:
        return None
    if choice == MANUAL_INPUT_LABEL:
        return custom or None
    return choice


def overrides_from_payload(fields: dict[str, dict[str, str]]) -> dict[str, str]:
    """fields: { key: { choice, custom? } }"""
    ov: dict[str, str] = {}
    wrap = fields.get("ai_patch_wrap", {})
    wrap_choice = wrap.get("choice", "")
    if wrap_choice in (AI_PATCH_WRAP_DISABLED, AI_PATCH_WRAP_ENABLED):
        ov["ai_patch_wrap"] = wrap_choice

    wrap_enabled = wrap_choice != AI_PATCH_WRAP_DISABLED
    vcs_choice = (fields.get("vcs") or {}).get("choice", "")

    for key, spec in {**FIELD_SPECS, **AI_FIELD_SPECS}.items():
        if key == "ai_patch_wrap":
            continue
        if key == "ai_patch_marker" and not wrap_enabled:
            continue
        if key == "default_branch" and vcs_choice == VCS_NONE:
            continue
        raw = fields.get(key, {})
        if spec.get("field_type") == "checkboxes":
            checked = raw.get("checked") or []
            if not isinstance(checked, list) or not checked:
                continue
            if len(checked) == 1 and checked[0] == NOT_SET_LABEL:
                continue
            if MANUAL_INPUT_LABEL in checked:
                custom = (raw.get("custom") or "").strip()
                if custom:
                    ov[key] = custom
                continue
            items = [
                item
                for item in checked
                if item not in SKIP_VALUES and item not in (NOT_SET_LABEL, MANUAL_INPUT_LABEL)
            ]
            if items:
                ov[key] = "\n".join(f"- {item}" for item in items)
            continue
        value = resolve_field_value(raw.get("choice", ""), raw.get("custom", ""))
        if value:
            ov[key] = value
    ov.update(advanced_to_overrides(fields.get("advanced")))
    return ov


def apply_changes_via_for_analysis(analysis: ExportAnalysis) -> str:
    if analysis.project_type == "edt":
        return "EDT"
    if analysis.project_type == "xml":
        return "Конфигуратор 1С (загрузка/сравнение выгрузки)"
    return ""


def analysis_hints(analysis: ExportAnalysis) -> dict[str, str]:
    hints: dict[str, str] = {}
    apply_via = apply_changes_via_for_analysis(analysis)
    if apply_via:
        hints["apply_changes_via"] = apply_via
    label = analysis.export_format_label or ""
    if "EDT" in label and not apply_via:
        hints["apply_changes_via"] = "EDT"
    elif "Конфигуратор" in label and not apply_via:
        hints["apply_changes_via"] = "Конфигуратор 1С (загрузка/сравнение выгрузки)"
    if analysis.script_variant == "Russian":
        hints["ai_explain_language"] = "Русский"
    elif analysis.script_variant == "English":
        hints["ai_explain_language"] = "Английский"
    prefix = (analysis.name_prefix or "").strip()
    if prefix:
        if prefix in PREFIX_OPTIONS:
            hints["dev_prefix"] = prefix
        else:
            hints["dev_prefix"] = MANUAL_INPUT_LABEL
            hints["dev_prefix_custom"] = prefix
    return hints


def _prefix_from_fields(fields: dict | None) -> str | None:
    if not fields:
        return None
    raw = fields.get("dev_prefix") or {}
    return resolve_field_value(raw.get("choice", ""), raw.get("custom", ""))


def _report_cell(value: str | None, *, empty: str = "—") -> str:
    if value is None:
        return empty
    text = str(value).strip()
    return text if text else empty


def _script_variant_report(value: str | None) -> str:
    if value == "Russian":
        return "русский (Russian)"
    if value == "English":
        return "английский (English)"
    return _report_cell(value)


def _run_mode_report(value: str | None) -> str:
    if value == "ManagedApplication":
        return "управляемое приложение (ManagedApplication)"
    if value == "OrdinaryApplication":
        return "обычное приложение (OrdinaryApplication)"
    return _report_cell(value)


def _dump_format_report(fmt: str | None) -> str:
    if not fmt:
        return "—"
    if fmt == "Hierarchical":
        return f"{fmt} — иерархическая выгрузка конфигуратора"
    return fmt


def _encoding_report(value: str | None) -> str:
    if value == "UTF-8-BOM":
        return "UTF-8 с BOM (по сигнатуре файлов)"
    if value == "UTF-8":
        return "UTF-8 (по сигнатуре)"
    return _report_cell(value)


def _format_name_prefix_line(analysis: ExportAnalysis, fields: dict | None) -> str:
    xml = (analysis.name_prefix or "").strip()
    form = (_prefix_from_fields(fields) or "").strip()
    if xml and form and xml != form:
        return f"Префикс имён (NamePrefix): {xml} в XML; в форме: {form}"
    if xml:
        return f"Префикс имён (NamePrefix): {xml} (из Configuration.xml)"
    if form:
        return f"Префикс имён (NamePrefix): {form} (в XML пусто, выбрано в форме)"
    return "Префикс имён (NamePrefix): не задан (в XML пусто; в форме «не задано»)"


def _format_bsl_regions(value: bool | None) -> str:
    if value is True:
        return "да — в .bsl найдены #Область / #Region"
    if value is False:
        return "нет — в просмотренных модулях маркеров областей нет"
    return "н/д — нет .bsl или файлы не прочитаны"


def _format_bsl_indent(value: bool | None) -> str:
    if value is True:
        return "табуляция — первая значимая строка с табом"
    if value is False:
        return "пробелы — первая значимая строка с отступом пробелами"
    return "н/д — нет .bsl или отступ по первой строке не определён"


def format_analysis_report(
    analysis: ExportAnalysis,
    *,
    form_fields: dict | None = None,
) -> str:
    platform = _report_cell(analysis.platform_hint)
    lines = [
        f"Каталог проекта: {analysis.export_path}",
        f"Тип проекта: {_report_cell(analysis.project_type_label)}",
        f"Валидный проект: {'да' if analysis.is_valid_export else 'нет'}",
        "",
    ]
    if analysis.project_type == "edt":
        lines.extend(
            [
                "=== Проект EDT ===",
                f"Имя конфигурации: {_report_cell(analysis.config_name)}",
                f"Синоним: {_report_cell(analysis.config_synonym)}",
                f"Версия конфигурации: {_report_cell(analysis.config_version)}",
                _format_name_prefix_line(analysis, form_fields),
                f"Язык скрипта: {_script_variant_report(analysis.script_variant)}",
                f"Режим совместимости: {_report_cell(analysis.compatibility_mode)}",
                "Совместимость расширений: "
                f"{_report_cell(analysis.extension_compatibility_mode)}",
                f"Ориентир версии платформы: {platform}",
                f"Режим запуска: {_run_mode_report(analysis.default_run_mode)}",
            ]
        )
    else:
        lines.extend(
            [
                "=== Configuration.xml ===",
                f"Имя конфигурации: {_report_cell(analysis.config_name)}",
                f"Синоним: {_report_cell(analysis.config_synonym)}",
                f"Версия конфигурации: {_report_cell(analysis.config_version)}",
                f"Поставщик: {_report_cell(analysis.config_vendor)}",
                f"Комментарий: {_report_cell(analysis.config_comment)}",
                _format_name_prefix_line(analysis, form_fields),
                f"Язык скрипта (ScriptVariant): {_script_variant_report(analysis.script_variant)}",
                f"Режим совместимости (CompatibilityMode): {_report_cell(analysis.compatibility_mode)}",
                "Совместимость расширений (ConfigurationExtensionCompatibilityMode): "
                f"{_report_cell(analysis.extension_compatibility_mode)}",
                f"Ориентир версии платформы: {platform}",
                f"Режим запуска (DefaultRunMode): {_run_mode_report(analysis.default_run_mode)}",
            ]
        )
    if analysis.project_type != "edt":
        lines.extend(
            [
                "",
                "=== ConfigDumpInfo.xml ===",
                f"Формат (format): {_dump_format_report(analysis.dump_format)}",
                f"Версия (version): {_report_cell(analysis.dump_version)}",
                f"Источник выгрузки: {_report_cell(analysis.export_format_label)}",
            ]
        )
    lines.extend(
        [
            "",
            "=== Files ===",
            f"Кодировка (эвристика): {_encoding_report(analysis.xml_encoding)}",
            f"Модулей .bsl: {analysis.bsl_module_count}",
            f"Директивы #Область / #Region в модулях: {_format_bsl_regions(analysis.bsl_uses_regions)}",
            f"Отступы в коде (таб / пробелы): {_format_bsl_indent(analysis.bsl_indent_tabs)}",
            "",
            "=== Metadata ===",
        ]
    )
    for lbl in sorted(analysis.metadata_counts.keys()):
        lines.append(
            f"  {lbl}: {analysis.metadata_counts[lbl]} — "
            f"{', '.join(analysis.metadata_objects[lbl])}"
        )
    if analysis.errors:
        lines.extend(["", "Ошибки:", *[f"  • {e}" for e in analysis.errors]])
    if analysis.warnings:
        lines.extend(["", "Предупреждения:", *[f"  • {w}" for w in analysis.warnings]])
    return "\n".join(lines)
