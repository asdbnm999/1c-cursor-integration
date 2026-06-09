"""Smoke-тесты §3 KB UI и API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from packages.kb.indexer.config import load_config
from web.app import app

PROFILE = "test-fixture"


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


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_kb_profile_page_has_docker_mem_slider(client, fixture_profile_config):
    res = client.get(f"/kb/profile/{PROFILE}")
    assert res.status_code == 200
    html = res.get_data(as_text=True)
    assert "kb-docker-mem-slider" in html
    assert "docker-compose-dir-input" in html
    assert 'id="btn-docker-pick-dir"' in html


def test_kb_docker_mem_limit_put(client, fixture_profile_config):
    with patch("web.routes.kb.require_indexed_profile"):
        res = client.put(
            f"/kb/api/profiles/{PROFILE}/docker/mem-limit",
            json={"mem_limit_mb": 2048},
        )
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["mem_limit_mb"] == 2048
    config = load_config(PROFILE)
    assert config.docker.mem_limit_mb == 2048


def test_kb_docker_pick_mcp_dir(client, fixture_profile_config, tmp_path: Path):
    parent = tmp_path / "mcp-root"
    parent.mkdir()

    with patch("web.routes.kb.require_indexed_profile"), patch(
        "packages.kb.indexer.native_dialogs.pick_directory",
        return_value=str(parent),
    ):
        res = client.post(f"/kb/api/profiles/{PROFILE}/docker/pick-mcp-dir", json={})

    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] is True
    assert body["compose_dir"] == str(parent / "1c-kb-test-fixture")
    assert (parent / "1c-kb-test-fixture").is_dir()
    config = load_config(PROFILE)
    assert config.docker.compose_dir == str(parent / "1c-kb-test-fixture")
