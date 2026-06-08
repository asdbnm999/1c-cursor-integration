"""Тесты прогресса deploy §2."""

from __future__ import annotations

import time

from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG
from web.mcp.deploy_jobs import (
    DeployJob,
    DeployJobStatus,
    _init_steps,
    compute_deploy_percent,
    deploy_step_plan,
    get_deploy_job,
    job_to_dict,
    start_deploy_job,
)


def test_deploy_step_plan_syntax_has_index_step():
    ids = [step_id for step_id, _, _ in deploy_step_plan(SYNTAX_SLUG)]
    assert "mcp_protocol" in ids
    assert "build" in ids


def test_compute_deploy_percent_running_health():
    steps = _init_steps(SYNTAX_SLUG)
    steps["prepare"]["status"] = "done"
    steps["clone"]["status"] = "done"
    steps["health"]["status"] = "running"
    steps["health"]["extra"] = {"elapsed": 60, "timeout": 300}
    pct = compute_deploy_percent(SYNTAX_SLUG, steps)
    assert 10 < pct < 60


def test_job_to_dict_orders_steps():
    job = DeployJob(id="test", server=SEARXNG_SLUG, steps=_init_steps(SEARXNG_SLUG))
    data = job_to_dict(job)
    assert data is not None
    assert data["server"] == SEARXNG_SLUG
    assert len(data["steps"]) == len(deploy_step_plan(SEARXNG_SLUG))
    assert data["steps"][0]["status"] == "pending"


def test_run_job_uses_job_id_not_undefined_job(monkeypatch):
    import web.mcp.deploy_jobs as deploy_jobs

    seen = {}

    def fake_run_deploy(server, **kwargs):
        seen["server"] = server
        return {"ok": True, "deploy": {"ok": True, "steps": []}}

    monkeypatch.setattr("web.mcp.service.run_deploy", fake_run_deploy)
    job = start_deploy_job(SYNTAX_SLUG, dry_run_mcp=True)
    for _ in range(40):
        time.sleep(0.05)
        current = get_deploy_job(job.id)
        if current and current.status in (DeployJobStatus.COMPLETED, DeployJobStatus.FAILED):
            break
    assert seen.get("server") == SYNTAX_SLUG


def test_deploy_job_finishes_with_result(monkeypatch):
    import web.mcp.deploy_jobs as deploy_jobs

    def fake_run_job(job_id: str, *, dry_run_mcp: bool = False) -> None:
        deploy_jobs._on_progress(job_id, "prepare", "start", None)
        deploy_jobs._on_progress(job_id, "prepare", "done", {"message": "compose готов"})
        with deploy_jobs._lock:
            job = deploy_jobs._jobs.get(job_id)
            if job:
                job.percent = 100
        deploy_jobs._update_job(
            job_id,
            status=deploy_jobs.DeployJobStatus.COMPLETED,
            result={
                "ok": True,
                "deploy": {"ok": True, "steps": [], "message": "Deploy завершён"},
                "refresh_hint": "Обновите MCP в Cursor",
            },
            progress_message="Deploy завершён",
            finished_at=deploy_jobs._now(),
        )

    monkeypatch.setattr(deploy_jobs, "_run_job", fake_run_job)
    job = start_deploy_job(SYNTAX_SLUG, dry_run_mcp=True)
    finished = None
    for _ in range(40):
        time.sleep(0.05)
        finished = get_deploy_job(job.id)
        if finished and finished.status in (DeployJobStatus.COMPLETED, DeployJobStatus.FAILED):
            break
    assert finished is not None
    assert finished.status == DeployJobStatus.COMPLETED
    assert finished.result is not None
    assert finished.result.get("ok") is True
    assert finished.percent == 100
