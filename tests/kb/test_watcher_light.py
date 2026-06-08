from unittest.mock import patch

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.watcher import _WatcherThread, start_watch, stop_watch


def test_watch_poll_uses_light_preview(fixture_profile_config):
    config = load_config(fixture_profile_config)
    watcher = _WatcherThread(config.profile_name)
    with patch("packages.kb.indexer.watcher.preview_incremental_light") as mock_preview:
        mock_preview.return_value = {"modified": [], "deleted": []}
        watcher._poll_once()
        mock_preview.assert_called_once()


def test_watch_persist_config(fixture_profile_config):
    name = load_config(fixture_profile_config).profile_name
    start_watch(name)
    cfg = load_config(name)
    assert cfg.watch.enabled is True
    stop_watch(name)
    cfg = load_config(name)
    assert cfg.watch.enabled is False
