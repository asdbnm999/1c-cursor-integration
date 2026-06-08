"""Общая логика взаимоисключающих чекбоксов «не задано» / «ручной ввод»."""

from __future__ import annotations

from .field_choices import MANUAL_INPUT_LABEL, NOT_SET_LABEL


def apply_checkbox_toggle(
    option: str,
    *,
    checked: bool,
    selected: set[str],
    not_set: str = NOT_SET_LABEL,
    manual: str = MANUAL_INPUT_LABEL,
) -> set[str]:
    """Возвращает новый набор отмеченных пунктов после клика по `option`."""
    if checked:
        if option == not_set:
            return {not_set}
        if option == manual:
            return {manual}
        out = {o for o in selected if o not in (not_set, manual)}
        out.add(option)
        return out
    return {o for o in selected if o != option}
