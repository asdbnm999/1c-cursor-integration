"""Мета-тесты приёмки ТЗ §15 / план шаг 8 — минимальные пороги покрытия."""

from __future__ import annotations

from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = Path(__file__).resolve().parent


def _count_tests_in_dir(path: Path) -> int:
    import ast

    total = 0
    for py in path.rglob("test_*.py"):
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
                total += 1
    return total


def test_kb_test_count_minimum_122():
    kb_count = _count_tests_in_dir(TESTS_DIR / "kb")
    assert kb_count >= 122, f"KB tests: {kb_count}, expected >= 122"


def test_required_test_modules_exist():
    required = [
        "test_docker_naming.py",
        "test_cursor_mcp.py",
        "test_mcp_compose.py",
        "test_plugins.py",
        "test_rules_api.py",
        "test_rules_import.py",
        "test_system_check.py",
        "test_integration_dashboard.py",
        "test_kb_ports.py",
        "test_mcp_section.py",
        "test_sections_status.py",
    ]
    for name in required:
        assert (TESTS_DIR / name).is_file(), f"Missing {name}"


def test_fixture_paths_documented():
    from tests.conftest import EDT_FIXTURE, XML_FIXTURE

    assert XML_FIXTURE.name == "ТестоваяВыгрузка"
    assert EDT_FIXTURE  # путь задаётся через ONEC_EDT_FIXTURE или дефолт Desktop/EDT-fixture


@pytest.mark.parametrize(
    "port,zone",
    [
        (8201, "82xx"),
        (8202, "82xx"),
        (8203, "82xx"),
        (8301, "83xx"),
    ],
)
def test_port_zones_tz71(port: int, zone: str):
    if zone == "82xx":
        assert 8200 <= port <= 8299
    else:
        assert 8300 <= port <= 8399
