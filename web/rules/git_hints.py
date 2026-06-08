"""Подсказки Git/СКВ для EDT-проектов (ТЗ §12.4)."""

from __future__ import annotations

import subprocess
from pathlib import Path


def _run_git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    return (result.stdout or "").strip() or None


def git_hints_for_path(project_path: str | Path) -> dict:
    path = Path(project_path).expanduser().resolve()
    git_dir = path / ".git"
    if not git_dir.exists():
        return {
            "is_git": False,
            "branch": None,
            "remote": None,
            "vcs_guess": None,
        }

    branch = _run_git(["branch", "--show-current"], path)
    remote = _run_git(["remote", "get-url", "origin"], path)
    if not remote:
        remotes = _run_git(["remote"], path)
        if remotes:
            first = remotes.splitlines()[0].strip()
            remote = _run_git(["remote", "get-url", first], path)

    return {
        "is_git": True,
        "branch": branch,
        "remote": remote,
        "vcs_guess": "Git",
    }
