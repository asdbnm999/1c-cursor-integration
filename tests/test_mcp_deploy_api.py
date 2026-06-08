"""API deploy jobs §2."""

from __future__ import annotations

import time

from web.app import create_app
from web.mcp.constants import SYNTAX_SLUG
from web.mcp.deploy_jobs import DeployJobStatus, get_deploy_job, start_deploy_job


def _patch_fast_deploy_job(monkeypatch):
    import web.mcp.deploy_jobs as deploy_jobs

    def fake_run_job(job_id: str, *, dry_run_mcp: bool = False) -> None:
        deploy_jobs._update_job(
            job_id,
            status=deploy_jobs.DeployJobStatus.COMPLETED,
            result={"ok": True, "deploy": {"ok": True, "steps": []}},
            progress_message="Deploy завершён",
            finished_at=deploy_jobs._now(),
        )

    monkeypatch.setattr(deploy_jobs, "_run_job", fake_run_job)


def test_deploy_job_status_api(monkeypatch):
    _patch_fast_deploy_job(monkeypatch)
    app = create_app()
    client = app.test_client()

    job = start_deploy_job(SYNTAX_SLUG, dry_run_mcp=True)
    for _ in range(40):
        time.sleep(0.05)
        current = get_deploy_job(job.id)
        if current and current.status in (DeployJobStatus.COMPLETED, DeployJobStatus.FAILED):
            break

    res = client.get(f"/mcp/api/deploy/jobs/{job.id}")
    assert res.status_code == 200
    data = res.get_json()
    assert data["ok"] is True
    assert data["job"]["status"] in ("completed", "failed")
    assert data["job"]["result"] is not None


def test_deploy_stream_sends_terminal_event(monkeypatch):
    _patch_fast_deploy_job(monkeypatch)
    app = create_app()
    client = app.test_client()

    job = start_deploy_job(SYNTAX_SLUG, dry_run_mcp=True)
    for _ in range(40):
        time.sleep(0.05)
        current = get_deploy_job(job.id)
        if current and current.status == DeployJobStatus.COMPLETED:
            break

    res = client.get(f"/mcp/api/deploy/jobs/{job.id}/stream")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "completed" in body
