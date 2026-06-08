from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.index_state import ensure_manifest, file_signature
from packages.kb.indexer.scanner import scan_profile


@dataclass
class LocalChanges:
    modified: list[str]
    deleted: list[str]
    message: str

    @property
    def total(self) -> int:
        return len(self.modified) + len(self.deleted)


def collect_local_changes(config: ProfileConfig) -> LocalChanges:
    """
    Сравнение текущих файлов профиля с manifest последней индексации.
    Работает без git: EDT без VCS, XML-выгрузка, копирование файлов и т.д.
    """
    manifest = ensure_manifest(config)
    known: dict[str, dict] = manifest.get("files", {})

    current: dict[str, dict[str, int]] = {}
    for entry in scan_profile(config):
        path = Path(entry.path).resolve()
        if not path.is_file():
            continue
        current[str(path)] = file_signature(path)

    modified: list[str] = []
    for path_str, sig in current.items():
        prev = known.get(path_str)
        if not prev or prev.get("mtime_ns") != sig["mtime_ns"] or prev.get("size") != sig["size"]:
            modified.append(path_str)

    deleted = sorted(path for path in known if path not in current)

    label = "EDT" if config.format == "edt" else "XML-выгрузка"
    msg = f"Локально ({label}): изменено {len(modified)}, удалено {len(deleted)}"
    return LocalChanges(modified=sorted(modified), deleted=deleted, message=msg)
