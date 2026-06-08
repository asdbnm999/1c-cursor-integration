"""Тесты ожидания индекса Syntax MCP."""

from __future__ import annotations

from web.mcp.deploy import syntax_index_error, syntax_index_ready, syntax_indexing_state


def test_syntax_indexing_state_reads_nested_status():
    payload = {"indexing": {"status": "in_progress", "progress_percent": 12.5}}
    assert syntax_indexing_state(payload) == "in_progress"


def test_syntax_index_ready_idle_with_documents():
    payload = {
        "documents_count": 24681,
        "index_exists": True,
        "indexing": {"status": "idle", "is_active": False},
    }
    assert syntax_index_ready(payload) is True


def test_syntax_index_ready_completed():
    payload = {"indexing": {"status": "completed"}, "documents_count": 100}
    assert syntax_index_ready(payload) is True


def test_syntax_index_not_ready_while_in_progress():
    payload = {"indexing": {"status": "in_progress"}, "documents_count": 0}
    assert syntax_index_ready(payload) is False


def test_syntax_index_error_on_failed():
    payload = {"indexing": {"status": "failed", "error_message": "ES OOM"}}
    assert syntax_index_error(payload) == "ES OOM"
