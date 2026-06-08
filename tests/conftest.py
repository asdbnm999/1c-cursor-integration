"""Общие фикстуры и пути для тестов 1C:Cursor (шаг 8)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Локальные фикстуры 1С: переопределите через ONEC_XML_FIXTURE / ONEC_EDT_FIXTURE
XML_FIXTURE = Path(
    os.environ.get(
        "ONEC_XML_FIXTURE",
        Path.home() / "Desktop" / "ДиректорияКурсора" / "ТестоваяВыгрузка",
    )
).expanduser()
EDT_FIXTURE = Path(
    os.environ.get("ONEC_EDT_FIXTURE", Path.home() / "Desktop" / "EDT-fixture")
).expanduser()

pytest_plugins = []


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "requires_xml_fixture: тест требует XML-выгрузку на Desktop",
    )
    config.addinivalue_line(
        "markers",
        "requires_edt_fixture: тест требует EDT-проект на Desktop",
    )


@pytest.fixture(scope="session")
def xml_fixture_path() -> Path:
    return XML_FIXTURE


@pytest.fixture(scope="session")
def edt_fixture_path() -> Path:
    return EDT_FIXTURE
