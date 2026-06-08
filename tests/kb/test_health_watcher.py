from unittest.mock import patch

from packages.kb.indexer.config import load_config
from packages.kb.indexer.health import health_for_profile
from packages.kb.indexer.watcher import get_watch_status, start_watch, stop_watch


def test_health_profile(fixture_profile_config):
    h = health_for_profile(load_config(fixture_profile_config).profile_name)
    assert "checks" in h
    assert "source" in h["checks"]
    assert "healthy" in h


def test_watcher_start_stop(fixture_profile_config):
    config = load_config(fixture_profile_config)
    name = config.profile_name
    status = start_watch(name)
    assert status["active"] is True
    status = stop_watch(name)
    assert status["active"] is False
    assert get_watch_status(name)["active"] is False
