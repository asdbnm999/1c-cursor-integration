from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.scanner import scan_profile

INDEXABLE_SUFFIXES = (".bsl", ".mdo", ".xml", ".md")


@dataclass
class GitChanges:
    modified: list[str]
    deleted: list[str]
    git_root: str
    message: str

    @property
    def total(self) -> int:
        return len(self.modified) + len(self.deleted)


def get_git_branch(start: Path) -> str:
    """Текущая ветка git для каталога проекта (пусто если git нет)."""
    root = find_git_root(start)
    if root is None:
        return ""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if result.returncode == 0:
            return (result.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def find_git_root(start: Path) -> Path | None:
    path = start.expanduser().resolve()
    if (path / ".git").is_dir():
        return path
    for parent in path.parents:
        if (parent / ".git").is_dir():
            return parent
    return None


def _is_indexable(path: Path) -> bool:
    return path.suffix.lower() in INDEXABLE_SUFFIXES and path.is_file()


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
    )


def collect_git_changes(start_path: Path) -> GitChanges:
    """Изменения относительно HEAD: staged, unstaged и untracked."""
    git_root = find_git_root(start_path)
    if git_root is None:
        return GitChanges([], [], "", "Git-репозиторий не найден рядом с проектом")

    modified: set[str] = set()
    deleted: set[str] = set()

    status = _run_git(git_root, "status", "--porcelain", "-u")
    if status.returncode != 0:
        return GitChanges([], [], str(git_root), status.stderr.strip() or "git status завершился с ошибкой")

    for line in status.stdout.splitlines():
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        path_part = line[3:].strip()
        if not path_part:
            continue

        if " -> " in path_part:
            old_path, new_path = path_part.split(" -> ", 1)
            old_abs = (git_root / old_path).resolve()
            deleted.add(str(old_abs))
            path_part = new_path

        abs_path = (git_root / path_part).resolve()

        if y == "D" or x == "D":
            deleted.add(str(abs_path))
            continue

        if x == "?" and y == "?":
            if _is_indexable(abs_path):
                modified.add(str(abs_path))
            continue

        if _is_indexable(abs_path):
            modified.add(str(abs_path))

    for rel in _run_git(git_root, "diff", "--name-only", "--diff-filter=D", "HEAD").stdout.splitlines():
        if not rel.strip():
            continue
        deleted.add(str((git_root / rel.strip()).resolve()))

    modified -= deleted
    msg = f"Git: {git_root} · изменено {len(modified)}, удалено {len(deleted)}"
    return GitChanges(
        modified=sorted(modified),
        deleted=sorted(deleted),
        git_root=str(git_root),
        message=msg,
    )


def _path_in_profile(config: ProfileConfig, path: str) -> bool:
    target = Path(path).resolve()
    for base in (config.root, config.source_base):
        base = base.resolve()
        if target == base or base in target.parents:
            return True
    if config.docs.enabled:
        for rel in config.docs.paths:
            docs_base = (config.root / rel).resolve()
            if target == docs_base or docs_base in target.parents:
                return True
    return False


def scope_changes_for_profile(config: ProfileConfig, changes: GitChanges) -> GitChanges:
    modified = [p for p in changes.modified if _path_in_profile(config, p)]
    deleted = [p for p in changes.deleted if _path_in_profile(config, p)]

    scan_paths = {str(Path(entry.path).resolve()) for entry in scan_profile(config)}
    modified = sorted(set(modified) & scan_paths)

    return GitChanges(
        modified=modified,
        deleted=sorted(deleted),
        git_root=changes.git_root,
        message=changes.message,
    )
