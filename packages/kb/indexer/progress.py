"""Прогресс индексации: файл X/Y, ETA, сообщения."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Protocol


PHASES = ("scanning", "chunking", "embedding", "upserting", "finalizing")


@dataclass
class IndexProgress:
    current_file: int = 0
    total_files: int = 0
    current_path: str = ""
    chunks_written: int = 0
    chunks_estimated: int = 0
    errors: int = 0
    message: str = ""
    phase: str = "scanning"
    eta_seconds: float | None = None
    started_at: float = field(default_factory=time.monotonic)

    def to_dict(self) -> dict:
        percent = 0.0
        if self.total_files:
            percent = round(100 * self.current_file / self.total_files, 1)
        elif self.chunks_estimated and self.chunks_written:
            percent = round(100 * self.chunks_written / self.chunks_estimated, 1)
        return {
            "current_file": self.current_file,
            "total_files": self.total_files,
            "current_path": self.current_path,
            "chunks_written": self.chunks_written,
            "chunks_estimated": self.chunks_estimated,
            "errors": self.errors,
            "message": self.message,
            "phase": self.phase,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds is not None else None,
            "percent": percent,
        }

    def set_phase(self, phase: str) -> None:
        if phase in PHASES:
            self.phase = phase

    def update_chunks_stats(self, *, produced: int, written: int, files_done: int) -> None:
        """Обновить счётчики чанков; оценка итога — экстраполяция по уже обработанным файлам."""
        self.chunks_written = written
        if files_done <= 0 or self.total_files <= 0:
            self.chunks_estimated = max(produced, written, 0)
            return
        projected = int(produced / files_done * self.total_files)
        self.chunks_estimated = max(produced, written, projected)

    def update_file(self, index: int, path: str, total: int) -> None:
        self.phase = "chunking"
        self.current_file = index
        self.total_files = total
        self.current_path = path
        elapsed = time.monotonic() - self.started_at
        if index > 0 and elapsed > 0:
            rate = index / elapsed
            remaining = total - index
            self.eta_seconds = remaining / rate if rate > 0 else None
        short = path.rsplit("/", 1)[-1] if path else ""
        eta_txt = ""
        if self.eta_seconds is not None and self.eta_seconds > 0:
            mins, secs = divmod(int(self.eta_seconds), 60)
            eta_txt = f", ETA ~{mins}м {secs}с" if mins else f", ETA ~{secs}с"
        self.message = f"Файл {index}/{total}: {short}{eta_txt}"


class ProgressCallback(Protocol):
    def __call__(self, progress: IndexProgress) -> None: ...
