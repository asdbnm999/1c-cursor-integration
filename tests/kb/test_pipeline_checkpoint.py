from pathlib import Path
from unittest.mock import MagicMock, patch

from packages.kb.indexer.checkpoint import clear_checkpoint, load_checkpoint
from packages.kb.indexer.config import load_config
from packages.kb.indexer.pipeline import _checkpoint_confirmed_paths, _flush_pending_chunks
from packages.kb.indexer.progress import IndexProgress


def test_checkpoint_confirmed_paths_filters_missing(fixture_profile_config):
    config = load_config(fixture_profile_config)
    with patch(
        "packages.kb.indexer.pipeline.path_has_chunks",
        side_effect=lambda _cfg, path: path.endswith("/saved.bsl"),
    ):
        confirmed = _checkpoint_confirmed_paths(
            config,
            ["/tmp/saved.bsl", "/tmp/missing.bsl"],
        )
    assert confirmed == [str(Path("/tmp/saved.bsl").resolve())]


def test_flush_pending_saves_checkpoint_only_after_upsert(fixture_profile_config):
    config = load_config(fixture_profile_config)
    clear_checkpoint(config)
    progress = IndexProgress()
    done_paths: list[str] = []
    chunk = MagicMock()
    chunk.embedding = [0.1]
    chunk.metadata = {"path": "/tmp/module.bsl"}
    chunk.id = "c1"
    chunk.text = "text"

    with (
        patch("packages.kb.indexer.pipeline._embed_batch", return_value=[chunk]),
        patch("packages.kb.indexer.pipeline.upsert_chunks") as upsert,
    ):
        written = _flush_pending_chunks(
            config,
            [chunk],
            progress=progress,
            on_progress=None,
            done_paths=done_paths,
            full=True,
        )

    assert written == 1
    upsert.assert_called_once()
    loaded = load_checkpoint(config)
    assert loaded is not None
    assert str(Path("/tmp/module.bsl").resolve()) in loaded["processed"]
    clear_checkpoint(config)
