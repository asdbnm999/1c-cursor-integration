"""Единый формат API-ошибок: {ok, error, error_code, details}."""

from __future__ import annotations

from typing import Any

from flask import jsonify

from packages.kb.indexer.api_auth import ApiAuthError
from packages.kb.indexer.exceptions import (
    ArchiveError,
    CompareError,
    ConfigValidationError,
    EmbeddingError,
    IndexEmptyError,
    IndexerError,
    IndexJobAlreadyRunningError,
    IndexJobCancelledError,
    IndexJobNotFoundError,
    ProfileNotFoundError,
    SourceNotFoundError,
    StoreError,
    WatchError,
    WizardError,
)

ERROR_CODES: dict[type[Exception], tuple[str, int]] = {
    ApiAuthError: ("AUTH_REQUIRED", 401),
    ProfileNotFoundError: ("PROFILE_NOT_FOUND", 404),
    SourceNotFoundError: ("SOURCE_NOT_FOUND", 400),
    IndexJobAlreadyRunningError: ("JOB_ALREADY_RUNNING", 409),
    IndexJobCancelledError: ("JOB_CANCELLED", 409),
    IndexJobNotFoundError: ("JOB_NOT_FOUND", 404),
    IndexEmptyError: ("INDEX_EMPTY", 400),
    ConfigValidationError: ("CONFIG_VALIDATION", 400),
    EmbeddingError: ("EMBEDDING_ERROR", 400),
    StoreError: ("STORE_ERROR", 500),
    WatchError: ("WATCH_ERROR", 400),
    ArchiveError: ("ARCHIVE_ERROR", 400),
    CompareError: ("COMPARE_ERROR", 400),
    WizardError: ("WIZARD_ERROR", 400),
    IndexerError: ("INDEXER_ERROR", 400),
    FileNotFoundError: ("FILE_NOT_FOUND", 404),
    FileExistsError: ("FILE_EXISTS", 409),
    ValueError: ("VALUE_ERROR", 400),
}


def error_code_for(exc: Exception) -> tuple[str, int]:
    for exc_type, mapping in ERROR_CODES.items():
        if isinstance(exc, exc_type):
            return mapping
    return ("INTERNAL_ERROR", 500)


def error_response(exc: Exception, *, ok: bool = False) -> tuple[Any, int]:
    code, status = error_code_for(exc)
    details = getattr(exc, "details", "") or ""
    payload: dict[str, Any] = {
        "ok": ok,
        "error": str(exc),
        "error_code": code,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status


def register_error_handlers(app) -> None:
    @app.errorhandler(IndexerError)
    def handle_indexer_error(exc: IndexerError):
        return error_response(exc)

    @app.errorhandler(404)
    def handle_not_found(exc):
        return jsonify({
            "ok": False,
            "error": "Ресурс не найден",
            "error_code": "NOT_FOUND",
        }), 404
