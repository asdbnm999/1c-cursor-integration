"""Фоновые задачи deploy §2 с прогрессом для UI."""

from __future__ import annotations

import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG

ProgressCallback = Callable[[str, str, dict[str, Any] | None], None]


class DeployJobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# (step_id, label, weight) — веса для общего прогресса
DEPLOY_STEP_PLANS: dict[str, list[tuple[str, str, int]]] = {
    SEARXNG_SLUG: [
        ("prepare", "Подготовка", 5),
        ("pull", "Загрузка образов", 18),
        ("up", "Запуск контейнеров", 12),
        ("health", "Health-check", 30),
        ("container", "Статус контейнера", 5),
        ("mcp_apply", "Применение mcp.json", 10),
    ],
    SYNTAX_SLUG: [
        ("prepare", "Подготовка", 4),
        ("clone", "Клонирование репозитория", 5),
        ("patch", "Патч MCP", 3),
        ("build", "Сборка образа", 22),
        ("up", "Запуск контейнеров", 10),
        ("health", "Health-check", 18),
        ("mcp_protocol", "MCP и индексация HBK", 28),
        ("container", "Статус контейнера", 4),
        ("mcp_apply", "Применение mcp.json", 6),
    ],
}


def deploy_step_plan(server: str) -> list[tuple[str, str, int]]:
    return DEPLOY_STEP_PLANS.get(server, DEPLOY_STEP_PLANS[SEARXNG_SLUG])


def compute_deploy_percent(server: str, steps_state: dict[str, dict[str, Any]]) -> int:
    plan = deploy_step_plan(server)
    total = sum(weight for _, _, weight in plan) or 1
    done = 0.0
    for step_id, _, weight in plan:
        status = (steps_state.get(step_id) or {}).get("status", "pending")
        if status == "done":
            done += weight
        elif status == "running":
            extra = (steps_state.get(step_id) or {}).get("extra") or {}
            elapsed = extra.get("elapsed")
            timeout = extra.get("timeout")
            if isinstance(elapsed, (int, float)) and isinstance(timeout, (int, float)) and timeout > 0:
                done += weight * min(0.95, elapsed / timeout)
            else:
                done += weight * 0.35
        elif status == "failed":
            done += weight * 0.15
    return min(100, max(0, int(done / total * 100)))


@dataclass
class DeployJob:
    id: str
    server: str
    status: DeployJobStatus = DeployJobStatus.PENDING
    current_step: str = ""
    steps: dict[str, dict[str, Any]] = field(default_factory=dict)
    percent: int = 0
    progress_message: str = ""
    error: str = ""
    result: dict[str, Any] | None = None
    started_at: str = ""
    finished_at: str = ""


_lock = threading.Lock()
_jobs: dict[str, DeployJob] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _init_steps(server: str) -> dict[str, dict[str, Any]]:
    return {
        step_id: {"id": step_id, "label": label, "status": "pending", "detail": ""}
        for step_id, label, _ in deploy_step_plan(server)
    }


def job_to_dict(job: DeployJob | None) -> dict[str, Any] | None:
    if job is None:
        return None
    plan = deploy_step_plan(job.server)
    ordered_steps = []
    for step_id, label, _ in plan:
        row = dict(job.steps.get(step_id) or {"id": step_id, "label": label, "status": "pending"})
        row.setdefault("label", label)
        ordered_steps.append(row)
    return {
        "id": job.id,
        "server": job.server,
        "status": job.status.value,
        "current_step": job.current_step,
        "percent": job.percent,
        "progress_message": job.progress_message,
        "steps": ordered_steps,
        "error": job.error,
        "result": job.result,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }


def get_deploy_job(job_id: str) -> DeployJob | None:
    with _lock:
        return _jobs.get(job_id)


def _update_job(job_id: str, **fields: Any) -> DeployJob | None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return None
        for key, value in fields.items():
            setattr(job, key, value)
        if job.status in (DeployJobStatus.COMPLETED, DeployJobStatus.FAILED):
            job.percent = 100
        else:
            job.percent = compute_deploy_percent(job.server, job.steps)
        return job


def _on_progress(job_id: str, step: str, phase: str, extra: dict[str, Any] | None = None) -> None:
    with _lock:
        job = _jobs.get(job_id)
        if not job:
            return
        plan_labels = {sid: label for sid, label, _ in deploy_step_plan(job.server)}
        row = job.steps.setdefault(
            step,
            {"id": step, "label": plan_labels.get(step, step), "status": "pending", "detail": ""},
        )
        if phase == "start":
            row["status"] = "running"
            row["detail"] = ""
            job.current_step = step
            job.progress_message = plan_labels.get(step, step) + "…"
        elif phase == "running":
            row["status"] = "running"
            row["extra"] = extra or {}
            elapsed = (extra or {}).get("elapsed")
            timeout = (extra or {}).get("timeout")
            if elapsed is not None and timeout:
                row["detail"] = f"{elapsed}с / ~{timeout}с"
            job.current_step = step
            job.progress_message = plan_labels.get(step, step) + "…"
        elif phase == "done":
            row["status"] = "done"
            row.pop("extra", None)
            detail = (extra or {}).get("message") or (extra or {}).get("detail") or ""
            if detail and detail != "OK":
                row["detail"] = str(detail)[:200]
        elif phase == "fail":
            row["status"] = "failed"
            row.pop("extra", None)
            row["detail"] = str((extra or {}).get("message") or (extra or {}).get("error") or "Ошибка")[:200]
        job.percent = compute_deploy_percent(job.server, job.steps)


def _run_job(job_id: str, *, dry_run_mcp: bool) -> None:
    from web.mcp.service import run_deploy

    job = get_deploy_job(job_id)
    if not job:
        return

    _update_job(job_id, status=DeployJobStatus.RUNNING, started_at=_now())
    callback: ProgressCallback = lambda step, phase, extra=None: _on_progress(job_id, step, phase, extra)
    try:
        result = run_deploy(job.server, apply_mcp=True, dry_run_mcp=dry_run_mcp, on_progress=callback)
        ok = bool(result.get("ok"))
        _update_job(
            job_id,
            status=DeployJobStatus.COMPLETED if ok else DeployJobStatus.FAILED,
            result=result,
            error="" if ok else (result.get("message") or "Deploy не удался"),
            progress_message="Deploy завершён" if ok else (result.get("message") or "Deploy не удался"),
            finished_at=_now(),
            current_step="",
        )
    except Exception as exc:
        _update_job(
            job_id,
            status=DeployJobStatus.FAILED,
            error=str(exc),
            progress_message=str(exc),
            finished_at=_now(),
            result={"ok": False, "message": str(exc), "trace": traceback.format_exc()[-2000:]},
        )


def start_deploy_job(server: str, *, dry_run_mcp: bool = False) -> DeployJob:
    job_id = uuid.uuid4().hex[:12]
    job = DeployJob(
        id=job_id,
        server=server,
        status=DeployJobStatus.PENDING,
        steps=_init_steps(server),
        started_at=_now(),
    )
    with _lock:
        _jobs[job_id] = job
    threading.Thread(
        target=_run_job,
        args=(job_id,),
        kwargs={"dry_run_mcp": dry_run_mcp},
        daemon=True,
        name=f"mcp-deploy-{job_id}",
    ).start()
    return job
