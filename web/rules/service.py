"""Бизнес-логика раздела §4 Правила."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from packages.rules import analyze_export, generate_rules_bundle
from packages.rules.advanced_rules import ADVANCED_SKIP_LABEL
from packages.rules.field_choices import (
    AI_PATCH_WRAP_DISABLED,
    ALL_FIELD_SPECS,
    MANUAL_INPUT_LABEL,
    NOT_SET_LABEL,
    VCS_NONE,
)
from packages.rules.form_api import apply_changes_via_for_analysis, overrides_from_payload
from packages.rules.mcp_rules import mcp_toggles_from_status
from packages.rules.rules_generator import default_rules_basename
from web.cursor_mcp import get_mcp_status
from web.settings import load_settings, save_settings


def resolve_output_path(
    analysis,
    *,
    project_path: Path,
    output_path: str | None,
    write_to_cursor_rules: bool,
) -> Path:
    if write_to_cursor_rules:
        base = default_rules_basename(analysis)
        return project_path / ".cursor" / "rules" / f"{base}.md"
    if output_path and output_path.strip():
        return Path(output_path.strip()).expanduser().resolve()
    base = default_rules_basename(analysis)
    return project_path.parent / f"{base}.md"


def validate_manual_fields(fields: dict[str, Any]) -> str | None:
    """Проверка ручного ввода и обязательных полей перед генерацией."""
    wrap_choice = (fields.get("ai_patch_wrap") or {}).get("choice", "")
    wrap_enabled = wrap_choice != AI_PATCH_WRAP_DISABLED
    vcs_choice = (fields.get("vcs") or {}).get("choice", "")

    for key, raw in fields.items():
        if key in ("advanced", "mcp"):
            continue
        if key == "ai_patch_marker" and not wrap_enabled:
            continue
        if key == "default_branch" and vcs_choice == VCS_NONE:
            continue
        spec = ALL_FIELD_SPECS.get(key, {})
        raw = raw or {}
        if spec.get("field_type") == "checkboxes":
            checked = raw.get("checked") or []
            if MANUAL_INPUT_LABEL in checked and not (raw.get("custom") or "").strip():
                return f"Для «{spec.get('label', key)}» выбран ручной ввод, но текст не заполнен."
            continue
        if raw.get("choice") == MANUAL_INPUT_LABEL and not (raw.get("custom") or "").strip():
            return f"Для «{spec.get('label', key)}» выбран ручной ввод, но текст не заполнен."
    return None


def validate_main_fields_complete(fields: dict[str, Any]) -> bool:
    """§12.3 блок 3: нет «— не задано —» в обязательных general/ai полях."""
    wrap_choice = (fields.get("ai_patch_wrap") or {}).get("choice", "")
    wrap_enabled = wrap_choice != AI_PATCH_WRAP_DISABLED
    vcs_choice = (fields.get("vcs") or {}).get("choice", "")

    required_keys = ("solution_type", "vcs", "dev_prefix")
    for key in required_keys:
        raw = fields.get(key) or {}
        choice = raw.get("choice", NOT_SET_LABEL)
        if choice == NOT_SET_LABEL or not choice:
            return False

    if vcs_choice != VCS_NONE:
        branch = (fields.get("default_branch") or {}).get("choice", NOT_SET_LABEL)
        if branch == NOT_SET_LABEL or not branch:
            return False

    for key, spec in ALL_FIELD_SPECS.items():
        if key in required_keys or key in ("default_branch", "apply_changes_via"):
            continue
        if key == "ai_patch_marker" and not wrap_enabled:
            continue
        if key == "default_branch" and vcs_choice == VCS_NONE:
            continue
        if spec.get("allow_not_set", True):
            continue
        raw = fields.get(key) or {}
        if spec.get("field_type") == "checkboxes":
            checked = raw.get("checked") or []
            if not checked:
                return False
            continue
        choice = raw.get("choice", "")
        if not choice:
            return False
    return True


def build_mcp_rules_payload(fields: dict[str, Any]) -> dict[str, Any]:
    mcp = fields.get("mcp") or {}
    status = get_mcp_status()
    toggles = mcp_toggles_from_status(status, user_overrides=mcp)
    return {
        "searxng": toggles["searxng"],
        "syntax_helper": toggles["syntax_helper"],
        "kb_profiles": toggles["kb_profiles"],
    }


def get_mcp_form_defaults(user_overrides: dict | None = None) -> dict[str, Any]:
    return mcp_toggles_from_status(get_mcp_status(), user_overrides=user_overrides)


def generate_rules(
    export_path: str,
    *,
    output_path: str | None = None,
    fields: dict[str, Any] | None = None,
    confirm_unsafe_wrap: bool = False,
    write_to_cursor_rules: bool = True,
) -> dict[str, Any]:
    fields = fields or {}
    path = Path(export_path).expanduser().resolve()
    analysis = analyze_export(path)

    if not analysis.is_valid_export:
        return {
            "ok": False,
            "error": "Проект не распознан.",
            "details": analysis.errors,
        }

    wrap_choice = (fields.get("ai_patch_wrap") or {}).get("choice", "")
    if wrap_choice == AI_PATCH_WRAP_DISABLED and not confirm_unsafe_wrap:
        return {
            "ok": False,
            "needs_confirm": True,
            "error": "Режим без обрамления небезопасен.",
        }

    field_error = validate_manual_fields(fields)
    if field_error:
        return {"ok": False, "error": field_error}

    overrides = overrides_from_payload(fields)
    overrides["apply_changes_via"] = apply_changes_via_for_analysis(analysis)
    mcp_rules = build_mcp_rules_payload(fields)

    out = resolve_output_path(
        analysis,
        project_path=path,
        output_path=output_path,
        write_to_cursor_rules=write_to_cursor_rules,
    )

    md, log_md, main_path, log_path = generate_rules_bundle(
        analysis,
        output_path=out,
        manual_overrides=overrides,
        mcp_rules=mcp_rules,
    )

    settings = load_settings()
    settings.setdefault("rules", {})["last_output"] = {
        "export_path": str(path),
        "main_path": str(main_path),
        "log_path": str(log_path),
        "project_type": analysis.project_type,
        "write_to_cursor_rules": write_to_cursor_rules,
    }
    settings["sections"]["rules"] = compute_rules_section_status(settings["rules"]["last_output"])
    save_settings(settings)

    return {
        "ok": True,
        "markdown": md,
        "output_path": str(main_path),
        "event_log_markdown": log_md,
        "event_log_path": str(log_path),
        "project_type": analysis.project_type,
    }


def compute_rules_section_status(last_output: dict[str, Any] | None) -> str:
    """§6.4: ready = оба .md существуют по последнему пути."""
    if not last_output:
        return "not_started"
    main = last_output.get("main_path")
    log = last_output.get("log_path")
    if not main or not log:
        return "in_progress"
    if Path(main).is_file() and Path(log).is_file():
        return "ready"
    return "in_progress"


def get_rules_status() -> dict[str, Any]:
    settings = load_settings()
    last = settings.get("rules", {}).get("last_output") or {}
    computed = compute_rules_section_status(last)
    stored = settings.get("sections", {}).get("rules", "not_started")
    if stored != computed:
        settings.setdefault("sections", {})["rules"] = computed
        save_settings(settings)
    return {
        "section_status": computed,
        "last_output": last,
        "computed_status": computed,
    }


def advanced_all_skipped(advanced: dict[str, str] | None, skip_label: str) -> bool:
    if not advanced:
        return True
    return all((v or skip_label) == skip_label for v in advanced.values())
