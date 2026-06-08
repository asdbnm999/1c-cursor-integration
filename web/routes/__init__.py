"""Flask-маршруты разделов 1C:Cursor."""

from __future__ import annotations

from flask import Blueprint, render_template

from web.sections import build_sections_snapshot, section_status_label


def create_blueprints() -> list[Blueprint]:
    blueprints: list[Blueprint] = []

    dashboard_bp = Blueprint("dashboard", __name__)

    @dashboard_bp.route("/")
    def index():
        snapshot = build_sections_snapshot(refresh=False)
        return render_template(
            "dashboard.html",
            page_subtitle="Настройка среды разработки 1С в Cursor",
            cards=snapshot["cards"],
            wizard_steps=snapshot["wizard_steps"],
            sections_summary=snapshot["summary"],
        )

    blueprints.append(dashboard_bp)
    return blueprints


# Re-export for backward compatibility in section blueprints
__all__ = ["create_blueprints", "section_status_label"]
