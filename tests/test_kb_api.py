"""Smoke-тесты §3 KB UI и API."""

from __future__ import annotations

from web.app import app


def test_kb_page_renders():
    client = app.test_client()
    res = client.get("/kb/")
    assert res.status_code == 200
    assert "Векторная база знаний".encode("utf-8") in res.data


def test_kb_api_system():
    client = app.test_client()
    res = client.get("/kb/api/system")
    assert res.status_code == 200
    data = res.get_json()
    assert "docker_available" in data


def test_kb_api_profiles_list():
    client = app.test_client()
    res = client.get("/kb/api/profiles")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)
