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
from packages.kb.indexer.incremental import preview_incremental


def _config(root: Path) -> ProfileConfig:
    return ProfileConfig(
        profile_name="t",
        display_name="T",
        format="xml_export",
        root=root,
        src="",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(),
        mcp=McpConfig(),
        docker=DockerConfig(),
        config_path=root / "config.yaml",
    )


def test_preview_without_git_uses_local(tmp_path: Path):
    root = tmp_path / "export"
    root.mkdir()
    config = _config(root)

    with patch("packages.kb.indexer.incremental.collect_local_changes") as mock_local:
        from packages.kb.indexer.local_changes import LocalChanges

        mock_local.return_value = LocalChanges(
            modified=[str(root / "Documents" / "A.xml")],
            deleted=[],
            message="local",
        )
        with patch("packages.kb.indexer.incremental.find_git_root", return_value=None):
            with patch("packages.kb.indexer.incremental.count_chunks", return_value=10):
                preview = preview_incremental(config)

    assert preview["git_available"] is False
    assert preview["source"] == "local"
    assert preview["format_label"] == "XML-выгрузка"
    assert preview["has_changes"] is True
