from __future__ import annotations

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.git_changes import collect_git_changes, find_git_root, scope_changes_for_profile
from packages.kb.indexer.local_changes import collect_local_changes
from packages.kb.indexer.exceptions import IndexEmptyError, IndexerError
from packages.kb.indexer.store import count_chunks


def _merge_paths(*groups: list[str]) -> list[str]:
    return sorted(set(groups[0]).union(*groups[1:])) if groups else []


def preview_incremental(config: ProfileConfig, *, include_chunk_count: bool = True) -> dict:
    local = collect_local_changes(config)
    git_root = find_git_root(config.root)
    git_scoped_modified: list[str] = []
    git_scoped_deleted: list[str] = []

    if git_root is not None:
        scoped = scope_changes_for_profile(config, collect_git_changes(config.root))
        git_scoped_modified = scoped.modified
        git_scoped_deleted = scoped.deleted

    modified = _merge_paths(local.modified, git_scoped_modified)
    deleted = sorted(set(local.deleted) | set(git_scoped_deleted) - set(modified))

    if git_root is not None and (git_scoped_modified or git_scoped_deleted):
        source = "local+git"
        source_label = "локальные файлы + git"
    elif git_root is not None:
        source = "local"
        source_label = "локальные файлы (git доступен, но изменений в status нет)"
    else:
        source = "local"
        source_label = "локальные файлы (без git)"

    format_label = "EDT" if config.format == "edt" else "XML-выгрузка"
    messages = [local.message]
    if git_root:
        messages.append(f"Git: {git_root}")
    else:
        messages.append("Git: не используется")

    return {
        "source": source,
        "source_label": source_label,
        "format": config.format,
        "format_label": format_label,
        "git_root": str(git_root) if git_root else "",
        "git_available": git_root is not None,
        "modified": modified,
        "deleted": deleted,
        "modified_count": len(modified),
        "deleted_count": len(deleted),
        "local_modified_count": len(local.modified),
        "local_deleted_count": len(local.deleted),
        "git_modified_count": len(git_scoped_modified),
        "git_deleted_count": len(git_scoped_deleted),
        "total_count": len(modified) + len(deleted),
        "has_changes": bool(modified or deleted),
        "project_root": str(config.root.resolve()),
        "message": " · ".join(messages),
        "indexed_chunks": count_chunks(config) if include_chunk_count else None,
    }


def preview_incremental_light(config: ProfileConfig) -> dict:
    """Лёгкий preview для watchdog — без обращения к Chroma."""
    return preview_incremental(config, include_chunk_count=False)


def resolve_incremental_paths(config: ProfileConfig) -> tuple[list[str], list[str], dict]:
    preview = preview_incremental(config)

    if preview["indexed_chunks"] <= 0:
        raise IndexEmptyError(
            "Коллекция пуста — сначала выполните полную индексацию",
        )

    if not preview["has_changes"]:
        raise IndexerError(
            f"Нет изменённых файлов ({preview['format_label']}, {preview['source_label']})",
        )

    return preview["modified"], preview["deleted"], preview
