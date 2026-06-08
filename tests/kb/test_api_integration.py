"""Integration-тесты Web API (Flask test client)."""

from __future__ import annotations

from pathlib import Path

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.profile_ops import delete_profile
from web.app import app

PROFILE = "test-fixture"


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


@pytest.fixture(autouse=True)
def no_api_token(monkeypatch):
    monkeypatch.delenv("KB_API_TOKEN", raising=False)


def test_system_endpoint(client):
    res = client.get("/kb/api/system")
    assert res.status_code == 200
    data = res.get_json()
    assert "docker_available" in data
    assert data.get("api_token_required") is False


def test_health_system(client):
    res = client.get("/kb/api/health")
    assert res.status_code == 200
    assert res.get_json().get("ok") is True


def test_list_profiles(client, fixture_profile_config):
    res = client.get("/kb/api/profiles")
    assert res.status_code == 200
    names = [p["name"] for p in res.get_json()]
    assert PROFILE in names


def test_get_profile(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["name"] == PROFILE
    assert "checkpoint" in data
    assert "embeddings" in data
    assert "gates" in data
    assert "docker_enabled" in data["gates"]
    assert "mcp_enabled" in data["gates"]


def test_profile_health(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/health")
    assert res.status_code == 200
    data = res.get_json()
    assert "state" in data
    assert "checks" in data


def test_scan_profile(client, fixture_profile_config):
    res = client.post(f"/kb/api/profiles/{PROFILE}/scan")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["total"] >= 1


def test_index_changes_preview(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/index/changes")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert "has_changes" in data


def test_checkpoint_get(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/checkpoint")
    assert res.status_code == 200
    assert "checkpoint" in res.get_json()


def test_watch_status(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/watch")
    assert res.status_code == 200
    data = res.get_json()
    assert "active" in data


def test_embeddings_check(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/embeddings/check")
    assert res.status_code == 200
    assert "ok" in res.get_json()


def test_put_embeddings(client, fixture_profile_config):
    res = client.put(
        f"/kb/api/profiles/{PROFILE}/embeddings",
        json={"device": "cpu", "provider": "local"},
    )
    assert res.status_code == 200
    assert res.get_json()["ok"] is True


def test_put_indexing_settings(client, fixture_profile_config):
    res = client.put(
        f"/kb/api/profiles/{PROFILE}/indexing",
        json={"include_forms": False},
    )
    assert res.status_code == 200
    assert res.get_json()["indexing"]["include_forms"] is False


def test_compare_profiles(client, fixture_profile_config):
    res = client.post(
        "/kb/api/profiles/compare",
        json={"profile_a": PROFILE, "profile_b": PROFILE},
    )
    assert res.status_code == 400
    assert res.get_json()["error_code"] == "COMPARE_ERROR"


def test_create_and_delete_profile(client, xml_export_tree):
    name = "api-int-temp"
    try:
        res = client.post(
            "/kb/api/profiles",
            json={
                "name": name,
                "root": str(xml_export_tree),
                "format": "xml_export",
                "include_forms": True,
            },
        )
        assert res.status_code == 200
        assert res.get_json()["profile"] == name

        res = client.get(f"/kb/api/profiles/{name}")
        assert res.status_code == 200

        res = client.delete(f"/kb/api/profiles/{name}")
        assert res.status_code == 200
    finally:
        delete_profile(name)


def test_profile_jobs_list(client, fixture_profile_config):
    res = client.get(f"/kb/api/profiles/{PROFILE}/jobs")
    assert res.status_code == 200
    assert isinstance(res.get_json(), list)


def test_profile_not_found(client):
    res = client.get("/kb/api/profiles/nonexistent-profile-xyz")
    assert res.status_code == 404


def test_wizard_preview_integration(client, xml_export_tree):
    res = client.post(
        "/kb/api/wizard/preview",
        json={"root": str(xml_export_tree), "include_forms": True},
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["detected_format"] == "xml_export"


def test_index_start_returns_job(client, fixture_profile_config, monkeypatch):
    from packages.kb.indexer.jobs import IndexJob, JobStatus

    def fake_start(profile_name, **kwargs):
        return IndexJob(
            id="integration-job",
            profile_name=profile_name,
            full=kwargs.get("full", True),
            incremental=kwargs.get("incremental", False),
            resume=kwargs.get("resume", False),
            status=JobStatus.PENDING,
        )

    monkeypatch.setattr("web.routes.kb.start_index_job", fake_start)
    res = client.post(f"/kb/api/profiles/{PROFILE}/index", json={"incremental": True})
    assert res.status_code == 200
    job = res.get_json()["job"]
    assert job["incremental"] is True


def test_get_job(client, fixture_profile_config, monkeypatch):
    from packages.kb.indexer.jobs import IndexJob, JobStatus

    job = IndexJob(
        id="job-get-test",
        profile_name=PROFILE,
        full=False,
        incremental=True,
        status=JobStatus.COMPLETED,
    )
    monkeypatch.setattr("web.routes.kb.get_job", lambda jid: job if jid == job.id else None)
    res = client.get("/kb/api/jobs/job-get-test")
    assert res.status_code == 200
    assert res.get_json()["job"]["id"] == "job-get-test"


def test_clone_profile_api(client, fixture_profile_config):
    target = "api-int-clone"
    try:
        res = client.post(
            f"/kb/api/profiles/{PROFILE}/clone",
            json={"target_name": target, "copy_index": False},
        )
        assert res.status_code == 200
        assert res.get_json()["profile"] == target
    finally:
        delete_profile(target)


def test_mcp_merge_requires_body(client, fixture_profile_config):
    res = client.post(
        f"/kb/api/profiles/{PROFILE}/mcp/merge",
        json={},
    )
    assert res.status_code in {200, 400}
