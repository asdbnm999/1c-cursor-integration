import json

import pytest

from packages.kb.indexer.exceptions import IndexJobNotFoundError
from packages.kb.indexer.jobs import cancel_job, job_to_dict, last_job_path, load_persisted_job, persist_job
from packages.kb.indexer.jobs import IndexJob, JobStatus


def test_persist_and_load_job(fixture_profile_config):
    from packages.kb.indexer.config import load_config

    config = load_config(fixture_profile_config)
    job = IndexJob(
        id="test-job-id",
        profile_name=config.profile_name,
        full=True,
        status=JobStatus.RUNNING,
        progress={"percent": 42, "phase": "chunking"},
    )
    persist_job(job)
    path = last_job_path(config.profile_name)
    assert path.exists()
    loaded = load_persisted_job(config.profile_name)
    assert loaded["id"] == "test-job-id"
    assert loaded["progress"]["percent"] == 42


def test_cancel_job_not_found():
    with pytest.raises(IndexJobNotFoundError):
        cancel_job("00000000-0000-0000-0000-000000000000")


def test_job_to_dict():
    job = IndexJob(id="x", profile_name="p", full=False, incremental=True)
    d = job_to_dict(job)
    assert d["incremental"] is True
    assert d["status"] == "pending"
