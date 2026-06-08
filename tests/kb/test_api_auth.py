import os

import pytest

from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_api_open_without_token(client, monkeypatch):
    monkeypatch.delenv("KB_API_TOKEN", raising=False)
    res = client.get("/kb/api/health")
    assert res.status_code == 200


def test_api_requires_token(client, monkeypatch):
    monkeypatch.setenv("KB_API_TOKEN", "secret-token")
    res = client.get("/kb/api/health")
    assert res.status_code == 401
    data = res.get_json()
    assert data["error_code"] == "AUTH_REQUIRED"


def test_api_accepts_bearer_token(client, monkeypatch):
    monkeypatch.setenv("KB_API_TOKEN", "secret-token")
    res = client.get(
        "/kb/api/health",
        headers={"Authorization": "Bearer secret-token"},
    )
    assert res.status_code == 200


def test_api_accepts_header_token(client, monkeypatch):
    monkeypatch.setenv("KB_API_TOKEN", "secret-token")
    res = client.get(
        "/kb/api/health",
        headers={"X-KB-API-Token": "secret-token"},
    )
    assert res.status_code == 200


def test_static_pages_without_token(client, monkeypatch):
    monkeypatch.setenv("KB_API_TOKEN", "secret-token")
    res = client.get("/kb/")
    assert res.status_code == 200
