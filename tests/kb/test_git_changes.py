from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

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
from packages.kb.indexer.git_changes import (
    GitChanges,
    _path_in_profile,
    collect_git_changes,
    find_git_root,
    scope_changes_for_profile,
)


def _config(root: Path) -> ProfileConfig:
    return ProfileConfig(
        profile_name="t",
        display_name="T",
        format="edt",
        root=root,
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(enabled=True, paths=["docs"]),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(),
        mcp=McpConfig(),
        docker=DockerConfig(),
        config_path=root / "config.yaml",
    )


def test_find_git_root(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    assert find_git_root(repo / "src" / "Documents") == repo.resolve()


def test_collect_git_changes_parses_porcelain(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".git").mkdir()
    src = repo / "src" / "CommonModules" / "M"
    src.mkdir(parents=True)
    bsl = src / "Module.bsl"
    bsl.write_text("// code", encoding="utf-8")

    porcelain = " M src/CommonModules/M/Module.bsl\n D src/Documents/Old/Ext/ObjectModule.bsl\n"
    with patch("packages.kb.indexer.git_changes._run_git") as mock_git:
        mock_git.side_effect = [
            type("R", (), {"returncode": 0, "stdout": porcelain, "stderr": ""})(),
            type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})(),
        ]
        changes = collect_git_changes(repo)

    assert str(bsl.resolve()) in changes.modified
    assert any("ObjectModule.bsl" in p for p in changes.deleted)


def test_scope_changes_for_profile(tmp_path: Path):
    config = _config(tmp_path)
    (tmp_path / "src").mkdir()
    inside = tmp_path / "src" / "Module.bsl"
    inside.write_text("", encoding="utf-8")
    outside = tmp_path / "other.bsl"
    outside.write_text("", encoding="utf-8")

    raw = GitChanges(
        modified=[str(inside.resolve()), str(outside.resolve())],
        deleted=[],
        git_root=str(tmp_path),
        message="",
    )

    with patch("packages.kb.indexer.git_changes.scan_profile") as mock_scan:
        from packages.kb.indexer.models import FileEntry, FileKind, SourceFormat

        mock_scan.return_value = [
            FileEntry(
                path=str(inside),
                kind=FileKind.BSL,
                source_name="Module.bsl",
                source_format=SourceFormat.EDT,
                relative_path="src/Module.bsl",
            )
        ]
        scoped = scope_changes_for_profile(config, raw)

    assert scoped.modified == [str(inside.resolve())]
    assert scoped.deleted == []


def test_path_in_profile_docs(tmp_path: Path):
    config = _config(tmp_path)
    docs_file = tmp_path / "docs" / "guide.md"
    docs_file.parent.mkdir(parents=True)
    docs_file.write_text("# x", encoding="utf-8")
    assert _path_in_profile(config, str(docs_file.resolve()))
