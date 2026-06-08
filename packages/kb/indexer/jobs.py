from __future__ import annotations

import json
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import (
    ConfigValidationError,
    IndexJobAlreadyRunningError,
    IndexJobCancelledError,
    IndexJobNotFoundError,
    IndexerError,
)
from packages.kb.indexer.pipeline import run_incremental_index, run_index
from packages.kb.indexer.progress import IndexProgress
from packages.kb.indexer.profiles import PROJECT_ROOT


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class IndexJob:
    id: str
    profile_name: str
    full: bool
    incremental: bool = False
    resume: bool = False
    status: JobStatus = JobStatus.PENDING
    progress_message: str = ""
    error: str = ""
    started_at: str = ""
    finished_at: str = ""
    stats: dict = field(default_factory=dict)
    progress: dict = field(default_factory=dict)
    cancel_requested: bool = False


_lock = threading.Lock()
_jobs: dict[str, IndexJob] = {}
_profile_jobs: dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def last_job_path(profile_name: str) -> Path:
    path = PROJECT_ROOT / "data" / "profiles" / profile_name / "last-job.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def job_to_dict(job: IndexJob | None) -> dict | None:
    if job is None:
        return None
    return {
        "id": job.id,
        "status": job.status.value,
        "full": job.full,
        "incremental": job.incremental,
        "resume": job.resume,
        "progress_message": job.progress_message,
        "progress": job.progress,
        "error": job.error,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
        "stats": job.stats,
        "cancel_requested": job.cancel_requested,
    }


def persist_job(job: IndexJob) -> None:
    payload = {
        "profile_name": job.profile_name,
        **(job_to_dict(job) or {}),
        "persisted_at": _now(),
    }
    try:
        last_job_path(job.profile_name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass


def load_persisted_job(profile_name: str) -> dict | None:
    path = last_job_path(profile_name)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def get_job(job_id: str) -> IndexJob | None:
    with _lock:
        return _jobs.get(job_id)


def get_profile_job(profile_name: str) -> IndexJob | None:
    with _lock:
        job_id = _profile_jobs.get(profile_name)
        return _jobs.get(job_id) if job_id else None


def clear_profile_jobs(profile_name: str) -> None:
    """Сбрасывает задачи индексации профиля из памяти (при удалении профиля)."""
    with _lock:
        job_id = _profile_jobs.pop(profile_name, None)
        if job_id:
            _jobs.pop(job_id, None)


def list_jobs(profile_name: str | None = None) -> list[IndexJob]:
    with _lock:
        jobs = list(_jobs.values())
    if profile_name:
        jobs = [j for j in jobs if j.profile_name == profile_name]
    return sorted(jobs, key=lambda j: j.started_at or "", reverse=True)


def cancel_job(job_id: str) -> IndexJob:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            raise IndexJobNotFoundError(f"Задача не найдена: {job_id}")
        if job.status not in {JobStatus.PENDING, JobStatus.RUNNING}:
            raise IndexerError(f"Задачу нельзя отменить в статусе {job.status.value}")
        job.cancel_requested = True
        job.progress_message = "Отмена…"
        persist_job(job)
        return job


def start_index_job(
    profile_name: str,
    *,
    full: bool = True,
    incremental: bool = False,
    resume: bool = False,
) -> IndexJob:
    if resume:
        full = True
        incremental = False
    if full and incremental:
        raise ConfigValidationError("Укажите либо полную, либо инкрементальную индексацию")
    if incremental:
        full = False
        resume = False

    with _lock:
        active = _profile_jobs.get(profile_name)
        if active:
            job = _jobs.get(active)
            if job and job.status in {JobStatus.PENDING, JobStatus.RUNNING}:
                raise IndexJobAlreadyRunningError(
                    "Индексация уже выполняется для этого профиля",
                )

    job = IndexJob(
        id=str(uuid.uuid4()),
        profile_name=profile_name,
        full=full,
        incremental=incremental,
        resume=resume,
    )
    with _lock:
        _jobs[job.id] = job
        _profile_jobs[profile_name] = job.id

    persist_job(job)
    thread = threading.Thread(target=_run_job, args=(job,), daemon=True)
    thread.start()
    return job


def _update_progress(job: IndexJob, progress: IndexProgress) -> None:
    job.progress = progress.to_dict()
    job.progress_message = progress.message
    persist_job(job)


def _should_cancel(job: IndexJob) -> bool:
    return job.cancel_requested


def _run_job(job: IndexJob) -> None:
    job.status = JobStatus.RUNNING
    job.started_at = _now()
    if job.incremental:
        job.progress_message = "Обновление по изменённым файлам…"
    elif job.resume:
        job.progress_message = "Возобновление полной индексации…"
    elif job.full:
        job.progress_message = "Полная индексация…"
    else:
        job.progress_message = "Индексация…"
    persist_job(job)

    def on_progress(p: IndexProgress) -> None:
        if _should_cancel(job):
            raise IndexJobCancelledError("Индексация отменена")
        _update_progress(job, p)

    try:
        config = load_config(job.profile_name)
        cancel_check = lambda: _should_cancel(job)
        if job.incremental:
            stats = run_incremental_index(
                config,
                on_progress=on_progress,
                should_cancel=cancel_check,
            )
            job.progress_message = stats.get("progress", {}).get(
                "message",
                f"Обновлено файлов: {stats.get('files_processed', 0)}",
            )
        else:
            stats = run_index(
                config,
                full=job.full,
                resume=job.resume,
                on_progress=on_progress,
                should_cancel=cancel_check,
            )
            job.progress_message = stats.get("progress", {}).get("message", "Готово")
        if _should_cancel(job):
            raise IndexJobCancelledError("Индексация отменена")
        job.status = JobStatus.COMPLETED
        job.stats = stats
        job.progress = stats.get("progress", job.progress)
        chunks = int(stats.get("chunks_in_collection") or stats.get("chunks") or 0)
        if chunks > 0:
            try:
                from packages.kb.indexer.profile_ops import ensure_default_compose_dir

                ensure_default_compose_dir(job.profile_name)
            except Exception:
                pass
    except IndexJobCancelledError as exc:
        job.status = JobStatus.CANCELLED
        job.error = str(exc)
        job.progress_message = "Отменено"
    except IndexerError as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.progress_message = "Ошибка"
        job.stats = {"traceback": traceback.format_exc()}
    except Exception as exc:
        job.status = JobStatus.FAILED
        job.error = str(exc)
        job.progress_message = "Ошибка"
        job.stats = {"traceback": traceback.format_exc()}
    finally:
        job.finished_at = _now()
        persist_job(job)
