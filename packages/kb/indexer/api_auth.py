"""Опциональная защита HTTP API токеном KB_API_TOKEN."""

from __future__ import annotations

import os
from functools import wraps

from flask import request

from packages.kb.indexer.exceptions import IndexerError


class ApiAuthError(IndexerError):
    """Неверный или отсутствующий API-токен."""


def api_token_configured() -> bool:
    return bool(os.getenv("KB_API_TOKEN", "").strip())


def _extract_token() -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("X-KB-API-Token") or "").strip()


def check_api_token() -> None:
    expected = os.getenv("KB_API_TOKEN", "").strip()
    if not expected:
        return
    provided = _extract_token()
    if not provided or provided != expected:
        raise ApiAuthError(
            "Требуется API-токен (Authorization: Bearer или заголовок X-KB-API-Token)",
        )


def register_api_auth(app) -> None:
    """Проверяет токен для /kb/api/* маршрутов, если KB_API_TOKEN задан."""

    @app.before_request
    def _require_api_token():
        if not request.path.startswith("/kb/api/"):
            return None
        if request.method == "OPTIONS":
            return None
        try:
            check_api_token()
        except ApiAuthError as exc:
            from packages.kb.indexer.api_errors import error_response

            return error_response(exc)
        return None
