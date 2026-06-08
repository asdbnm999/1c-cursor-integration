from __future__ import annotations

import time
from pathlib import Path

from packages.kb.indexer.config import (
    ProfileConfig,
    ChunkingConfig,
    DocsConfig,
    DockerConfig,
    EmbeddingsConfig,
    IndexingConfig,
    McpConfig,
    StoreConfig,
)
from packages.kb.indexer.index_state import load_manifest, save_manifest_from_scan
from packages.kb.indexer.local_changes import collect_local_changes
from packages.kb.indexer.models import FileEntry, FileKind, SourceFormat


def _config(root: Path, fmt: str = "edt") -> ProfileConfig:
    return ProfileConfig(
        profile_name="t",
        display_name="T",
        format=fmt,
        root=root,
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(enabled=False),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path="data/profiles/t/chroma", collection="t"),
        mcp=McpConfig(),
        docker=DockerConfig(),
        config_path=root / "config.yaml",
        project_root=root.parent if root.name == "proj" else root,
    )


def test_local_changes_detects_mtime(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "kb"
    project_root.mkdir()
    root = project_root / "proj"
    src = root / "src"
    src.mkdir(parents=True)
    bsl = src / "Module.bsl"
    bsl.write_text("// v1", encoding="utf-8")

    config = _config(root)
    config.project_root = project_root

    with monkeypatch.context() as m:
        entry = FileEntry(
            path=str(bsl),
            kind=FileKind.BSL,
            source_name="Module.bsl",
            source_format=SourceFormat.EDT,
            relative_path="src/Module.bsl",
        )
        m.setattr("packages.kb.indexer.local_changes.scan_profile", lambda cfg: [entry])
        m.setattr("packages.kb.indexer.index_state.scan_profile", lambda cfg: [entry])
        save_manifest_from_scan(config)
        before = collect_local_changes(config)
        assert before.total == 0

        time.sleep(0.02)
        bsl.write_text("// v2", encoding="utf-8")
        after = collect_local_changes(config)
        assert str(bsl.resolve()) in after.modified


def test_local_changes_detects_deleted_file(tmp_path: Path, monkeypatch):
    project_root = tmp_path / "kb"
    project_root.mkdir()
    root = project_root / "xml"
    root.mkdir()
    xml = root / "Documents" / "Doc.xml"
    xml.parent.mkdir(parents=True)
    xml.write_text("<Document/>", encoding="utf-8")
    path_str = str(xml.resolve())

    config = _config(root, fmt="xml_export")
    config.project_root = project_root

    entry = FileEntry(
        path=path_str,
        kind=FileKind.METADATA,
        source_name="Doc.xml",
        source_format=SourceFormat.XML_EXPORT,
        relative_path="Documents/Doc.xml",
    )

    with monkeypatch.context() as m:
        m.setattr("packages.kb.indexer.local_changes.scan_profile", lambda cfg: [entry])
        m.setattr("packages.kb.indexer.index_state.scan_profile", lambda cfg: [entry])
        save_manifest_from_scan(config)

        xml.unlink()
        m.setattr("packages.kb.indexer.local_changes.scan_profile", lambda cfg: [])

        changes = collect_local_changes(config)
        assert path_str in changes.deleted


def test_manifest_bootstrap_empty_when_no_index(tmp_path: Path):
    project_root = tmp_path / "kb"
    project_root.mkdir()
    root = project_root / "proj"
    root.mkdir()
    config = _config(root)
    config.project_root = project_root

    data = load_manifest(config)
    assert data.get("files") == {}
