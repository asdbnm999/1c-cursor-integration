from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from packages.kb.indexer.workflow_guards import require_container_for_mcp, require_indexed_profile
from web.app import app

PROFILE = "test-fixture"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_docker_build_requires_index(client, fixture_profile_config):
    with patch("web.routes.kb.require_indexed_profile", side_effect=ValueError("Сначала выполните полную индексацию")):
        res = client.post(f"/kb/api/profiles/{PROFILE}/docker/build", json={})
    assert res.status_code == 400
    assert "индексац" in res.get_json()["error"]


def test_mcp_apply_requires_container(client, fixture_profile_config):
    with patch("web.routes.kb.require_container_for_mcp", side_effect=ValueError("Сначала соберите образ и запустите контейнер")):
        res = client.post(f"/kb/api/profiles/{PROFILE}/mcp/apply")
    assert res.status_code == 400
    assert "контейнер" in res.get_json()["error"]


def test_require_indexed_profile_raises_when_empty(monkeypatch, fixture_profile_config):
    monkeypatch.setattr("packages.kb.indexer.workflow_guards.profile_chunks", lambda _cfg: 0)
    with pytest.raises(ValueError, match="индексац"):
        require_indexed_profile(PROFILE)


def test_require_container_for_mcp_raises_when_missing(monkeypatch, fixture_profile_config):
    monkeypatch.setattr("packages.kb.indexer.workflow_guards.container_created", lambda _name: False)
    with pytest.raises(ValueError, match="контейнер"):
        require_container_for_mcp(PROFILE)
