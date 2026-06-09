"""Acceptance-тесты 4 сценариев MCP KB."""

from __future__ import annotations

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.kb_index import build_kb_index
from packages.kb.indexer.object_detail import get_object_detail
from packages.kb.indexer.relations import list_by_relation


@pytest.fixture(scope="module")
def acceptance_profile():
    for name in ("testbase2", "testbase", "test-base"):
        try:
            return load_config(name)
        except Exception:
            continue
    pytest.skip("Профиль testbase/testbase2/test-base недоступен для acceptance-тестов")


@pytest.fixture(scope="module")
def acceptance_kb(acceptance_profile):
    build_kb_index(acceptance_profile)
    return acceptance_profile


def test_scenario1_document_movements(acceptance_kb):
    result = get_object_detail(
        acceptance_kb, "Document", "РасходнаяНакладная", detail="movements"
    )
    assert "ОстаткиНоменклатуры" in result
    assert "Расход" in result
    assert "Номенклатура" in result
    assert "Партия" in result
    assert "ОбработкаПроведения" in result


def test_scenario2_documents_by_register(acceptance_kb):
    result = list_by_relation(
        acceptance_kb,
        "documents_by_register",
        object_type="AccumulationRegister",
        object_name="ОстаткиНоменклатуры",
    )
    assert "ПриходнаяНакладная" in result
    assert "Приход" in result
    assert "РасходнаяНакладная" in result
    assert "Расход" in result


def test_scenario3_document_posting(acceptance_kb):
    result = get_object_detail(
        acceptance_kb, "Document", "РасходнаяНакладная", detail="posting"
    )
    assert "ОбработкаПроведения" in result
    assert "ObjectModule.bsl" in result
    assert "FIFO" in result.upper()
    assert "ОстаткиНоменклатуры" in result


def test_scenario4_register_structure(acceptance_kb):
    result = get_object_detail(
        acceptance_kb, "AccumulationRegister", "ОстаткиНоменклатуры", detail="structure"
    )
    assert "Balance" in result
    assert "Номенклатура" in result
    assert "Партия" in result
    assert "Количество" in result
    assert "Сумма" in result
