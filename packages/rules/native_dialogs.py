"""Системные диалоги выбора папки/файла (локальный запуск сервера)."""

from __future__ import annotations

import platform
import subprocess
import sys
import threading
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

# Таймаут диалога (пользователь может долго выбирать путь)
DIALOG_TIMEOUT_SEC = 600


def _escape_applescript_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _run_osascript(script: str, *, timeout: int = DIALOG_TIMEOUT_SEC) -> tuple[int, str]:
    result = subprocess.run(
        ["osascript", "-"],
        input=script,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return result.returncode, (result.stdout or "").strip()


def _with_keepalive(work: Callable[[], T | None], keepalive: Callable[[], None] | None) -> T | None:
    """Сбрасывает таймер «пульса» веб-сервера, пока открыт системный диалог."""
    if not keepalive:
        return work()

    stop = threading.Event()

    def _pulse() -> None:
        while not stop.wait(8):
            keepalive()

    keepalive()
    pulse = threading.Thread(target=_pulse, daemon=True)
    pulse.start()
    try:
        return work()
    finally:
        stop.set()
        pulse.join(timeout=1)
        keepalive()


def _pick_via_tk(dialog: str, title: str, default_name: str = "") -> str | None:
    """Tkinter в отдельном процессе — только не macOS (на Mac часто зависает без окна)."""
    code = f"""
import tkinter as tk
from tkinter import filedialog
root = tk.Tk()
root.withdraw()
root.update()
try:
    root.attributes("-topmost", True)
except tk.TclError:
    pass
root.lift()
root.focus_force()
title = {title!r}
path = None
if {dialog!r} == "directory":
    path = filedialog.askdirectory(title=title, mustexist=True)
elif {dialog!r} == "save":
    path = filedialog.asksaveasfilename(
        title=title,
        defaultextension=".md",
        initialfile={default_name!r},
        filetypes=[("Markdown", "*.md"), ("Все файлы", "*.*")],
    )
print(path or "")
root.destroy()
"""
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            timeout=DIALOG_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return None
    if result.returncode != 0:
        return None
    path = result.stdout.strip()
    return path or None


def _pick_directory_macos(title: str) -> str | None:
    safe_title = _escape_applescript_string(title)
    script = f'''tell application "System Events" to activate
set theFolder to choose folder with prompt "{safe_title}"
POSIX path of theFolder
'''
    code, out = _run_osascript(script)
    if code != 0:
        return None
    return out or None


def _pick_save_macos(title: str, default_name: str) -> str | None:
    safe_title = _escape_applescript_string(title)
    safe_name = _escape_applescript_string(default_name)
    script = f'''tell application "System Events" to activate
set defaultName to "{safe_name}"
set theFile to choose file name defaultName with prompt "{safe_title}"
POSIX path of theFile
'''
    code, out = _run_osascript(script)
    if code != 0:
        return None
    if out and not out.lower().endswith(".md"):
        out += ".md"
    return out or None


def pick_directory(
    title: str = "Каталог XML-выгрузки 1С",
    *,
    keepalive: Callable[[], None] | None = None,
) -> str | None:
    def _work() -> str | None:
        if platform.system() == "Darwin":
            return _pick_directory_macos(title)
        return _pick_via_tk("directory", title)

    return _with_keepalive(_work, keepalive)


def pick_save_file(
    title: str = "Сохранить файл правил",
    default_name: str = "1С-XML-правила-разработки.md",
    *,
    keepalive: Callable[[], None] | None = None,
) -> str | None:
    def _work() -> str | None:
        if platform.system() == "Darwin":
            # На macOS не используем tk — подпроцесс часто «висит» без окна
            return _pick_save_macos(title, default_name)
        return _pick_via_tk("save", title, default_name)

    return _with_keepalive(_work, keepalive)
