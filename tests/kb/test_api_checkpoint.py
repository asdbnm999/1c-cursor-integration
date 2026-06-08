import pytest

from packages.kb.indexer.checkpoint import clear_checkpoint, save_checkpoint
from packages.kb.indexer.config import load_config
from web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_profile_includes_checkpoint(fixture_profile_config, client):
    config = load_config("test-fixture")
    clear_checkpoint(config)
    res = client.get("/kb/api/profiles/test-fixture")
    assert res.status_code == 200
    data = res.get_json()
    assert data["checkpoint"] is None

    save_checkpoint(config, processed_paths=["/a.bsl"], phase="indexing", full=True)
    try:
        res = client.get("/kb/api/profiles/test-fixture")
        cp = res.get_json()["checkpoint"]
        assert cp["available"] is True
        assert cp["processed_count"] == 1

        res = client.get("/kb/api/profiles/test-fixture/checkpoint")
        assert res.get_json()["checkpoint"]["processed_count"] == 1

        res = client.delete("/kb/api/profiles/test-fixture/checkpoint")
        assert res.get_json()["ok"] is True
        res = client.get("/kb/api/profiles/test-fixture/checkpoint")
        assert res.get_json()["checkpoint"] is None
    finally:
        clear_checkpoint(config)


def test_index_resume_flag(fixture_profile_config, client, monkeypatch):
    captured = {}

    def fake_start(profile_name, *, full=False, incremental=False, resume=False):
        captured.update(
            full=full,
            incremental=incremental,
            resume=resume,
            profile=profile_name,
        )
        from packages.kb.indexer.jobs import IndexJob, JobStatus

        return IndexJob(
            id="test-job",
            profile_name=profile_name,
            full=full,
            incremental=incremental,
            resume=resume,
            status=JobStatus.PENDING,
        )

    monkeypatch.setattr("web.routes.kb.start_index_job", fake_start)
    res = client.post(
        "/kb/api/profiles/test-fixture/index",
        json={"resume": True},
    )
    assert res.status_code == 200
    assert captured["resume"] is True
    assert captured["full"] is True
    assert captured["incremental"] is False
    job = res.get_json()["job"]
    assert job["resume"] is True
