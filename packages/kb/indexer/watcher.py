"""Файловый наблюдатель для авто-инкрементальной индексации."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import IndexJobAlreadyRunningError, WatchError
from packages.kb.indexer.incremental import preview_incremental_light
from packages.kb.indexer.jobs import get_profile_job, start_index_job
from packages.kb.indexer.profile_ops import save_watch_settings

logger = logging.getLogger(__name__)


@dataclass
class WatchState:
    profile_name: str
    active: bool = False
    last_trigger: str = ""
    last_error: str = ""
    debounce_pending: bool = False
    poll_count: int = 0
    started_at: str = ""
    pending_changes: bool = False


_lock = threading.Lock()
_watchers: dict[str, _WatcherThread] = {}


def _watch_log_path(profile_name: str) -> Path:
    from packages.kb.indexer.profiles import PROJECT_ROOT

    path = PROJECT_ROOT / "data" / "profiles" / profile_name / "watch.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _log_watch(profile_name: str, message: str) -> None:
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {message}\n"
    try:
        with _watch_log_path(profile_name).open("a", encoding="utf-8") as handle:
            handle.write(line)
    except OSError as exc:
        logger.warning("Watch log %s: %s", profile_name, exc)


class _WatcherThread:
    def __init__(self, profile_name: str) -> None:
        self.profile_name = profile_name
        self.state = WatchState(profile_name=profile_name)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_snapshot: tuple[frozenset[str], frozenset[str]] | None = None
        self._debounce_timer: threading.Timer | None = None
        self._poll_interval = 2.0
        self._debounce_seconds = 3.0
        self._mode = "poll"

    def start(self) -> WatchState:
        config = load_config(self.profile_name)
        self._poll_interval = max(1.0, config.watch.poll_interval_sec)
        self._debounce_seconds = max(1.0, config.watch.debounce_sec)
        self._mode = config.watch.mode or "poll"

        if self._thread and self._thread.is_alive():
            self.state.active = True
            return self.state
        self._stop.clear()
        self.state.active = True
        self.state.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        save_watch_settings(self.profile_name, enabled=True)
        _log_watch(self.profile_name, f"watch started (mode={self._mode})")
        return self.state

    def stop(self) -> WatchState:
        self._stop.set()
        self.state.active = False
        if self._debounce_timer:
            self._debounce_timer.cancel()
            self._debounce_timer = None
        save_watch_settings(self.profile_name, enabled=False)
        _log_watch(self.profile_name, "watch stopped")
        return self.state

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except WatchError as exc:
                self.state.last_error = str(exc)
                _log_watch(self.profile_name, f"fatal: {exc}")
                logger.error("Watch %s: %s", self.profile_name, exc)
                self.stop()
                break
            except Exception as exc:
                self.state.last_error = str(exc)
                logger.warning("Watch %s: %s", self.profile_name, exc)
            self._stop.wait(self._poll_interval)

    def _poll_once(self) -> None:
        self.state.poll_count += 1
        config = load_config(self.profile_name)
        base = config.source_base
        if not base.exists():
            raise WatchError(
                "Каталог проекта недоступен",
                details=str(base),
            )

        preview = preview_incremental_light(config)
        modified = frozenset(preview.get("modified") or [])
        deleted = frozenset(preview.get("deleted") or [])
        snapshot = (modified, deleted)

        if self._last_snapshot is None:
            self._last_snapshot = snapshot
            return

        if snapshot == self._last_snapshot:
            return

        if not modified and not deleted:
            self._last_snapshot = snapshot
            return

        self._last_snapshot = snapshot
        self.state.pending_changes = True
        _log_watch(
            self.profile_name,
            f"changes detected: modified={len(modified)} deleted={len(deleted)}",
        )
        self._schedule_index()

    def _on_filesystem_change(self) -> None:
        self.state.pending_changes = True
        _log_watch(self.profile_name, "filesystem event")
        self._schedule_index()

    def _schedule_index(self) -> None:
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self.state.debounce_pending = True

        def fire() -> None:
            self.state.debounce_pending = False
            self._trigger_index()

        self._debounce_timer = threading.Timer(self._debounce_seconds, fire)
        self._debounce_timer.daemon = True
        self._debounce_timer.start()

    def _trigger_index(self) -> None:
        job = get_profile_job(self.profile_name)
        if job and job.status.value in {"pending", "running"}:
            self.state.pending_changes = True
            _log_watch(self.profile_name, "index job active — changes queued")
            return
        try:
            start_index_job(self.profile_name, incremental=True)
            self.state.last_trigger = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            self.state.last_error = ""
            self.state.pending_changes = False
            _log_watch(self.profile_name, "incremental job started")
        except IndexJobAlreadyRunningError:
            self.state.pending_changes = True
        except Exception as exc:
            self.state.last_error = str(exc)
            _log_watch(self.profile_name, f"trigger failed: {exc}")


class _WatchdogThread(_WatcherThread):
    """Watch через библиотеку watchdog (inotify/FSEvents)."""

    def _run(self) -> None:
        try:
            from watchdog.events import PatternMatchingEventHandler
            from watchdog.observers import Observer
        except ImportError:
            self.state.last_error = "Пакет watchdog не установлен — fallback на poll"
            _log_watch(self.profile_name, "watchdog unavailable, fallback poll")
            self._mode = "poll"
            super()._run()
            return

        config = load_config(self.profile_name)
        base = config.source_base
        if not base.exists():
            raise WatchError("Каталог проекта недоступен", details=str(base))

        outer = self

        class _Handler(PatternMatchingEventHandler):
            def on_any_event(self, event) -> None:
                if event.is_directory or outer._stop.is_set():
                    return
                outer._on_filesystem_change()

        handler = _Handler(
            patterns=["*.bsl", "*.mdo", "*.xml", "*.md"],
            ignore_directories=True,
        )
        observer = Observer()
        observer.schedule(handler, str(base), recursive=True)
        observer.start()
        _log_watch(self.profile_name, "watchdog observer started")

        try:
            while not self._stop.is_set():
                self._stop.wait(0.5)
        finally:
            observer.stop()
            observer.join(timeout=5)
            _log_watch(self.profile_name, "watchdog observer stopped")


def _new_watcher(profile_name: str) -> _WatcherThread:
    try:
        config = load_config(profile_name)
        if (config.watch.mode or "poll") == "watchdog":
            return _WatchdogThread(profile_name)
    except Exception:
        pass
    return _WatcherThread(profile_name)


def start_watch(profile_name: str) -> dict:
    with _lock:
        watcher = _watchers.get(profile_name)
        if watcher is None:
            watcher = _new_watcher(profile_name)
            _watchers[profile_name] = watcher
        state = watcher.start()
    return _state_dict(state)


def stop_watch(profile_name: str) -> dict:
    with _lock:
        watcher = _watchers.get(profile_name)
        if watcher is None:
            save_watch_settings(profile_name, enabled=False)
            return {"profile_name": profile_name, "active": False}
        state = watcher.stop()
    return _state_dict(state)


def get_watch_status(profile_name: str) -> dict:
    with _lock:
        watcher = _watchers.get(profile_name)
        if watcher is None:
            try:
                config = load_config(profile_name)
                enabled = config.watch.enabled
            except Exception:
                enabled = False
            try:
                mode = load_config(profile_name).watch.mode
            except Exception:
                mode = "poll"
            return {
                "profile_name": profile_name,
                "active": False,
                "configured": enabled,
                "mode": mode,
            }
        return _state_dict(watcher.state)


def restore_watchers() -> list[str]:
    """Восстанавливает watchers с watch.enabled=true при старте kb-web."""
    from packages.kb.indexer.profiles import list_profiles

    restored: list[str] = []
    for name in list_profiles():
        try:
            config = load_config(name)
            if config.watch.enabled:
                start_watch(name)
                restored.append(name)
        except Exception as exc:
            logger.warning("Не удалось восстановить watch для %s: %s", name, exc)
    return restored


def _state_dict(state: WatchState) -> dict:
    watcher = _watchers.get(state.profile_name)
    mode = getattr(watcher, "_mode", "poll") if watcher else "poll"
    return {
        "profile_name": state.profile_name,
        "active": state.active,
        "mode": mode,
        "last_trigger": state.last_trigger,
        "last_error": state.last_error,
        "debounce_pending": state.debounce_pending,
        "poll_count": state.poll_count,
        "started_at": state.started_at,
        "pending_changes": state.pending_changes,
    }
