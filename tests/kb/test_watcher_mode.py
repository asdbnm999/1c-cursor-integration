from packages.kb.indexer.config import load_config
from packages.kb.indexer.watcher import _new_watcher, _WatcherThread, _WatchdogThread


def test_new_watcher_poll_mode(fixture_profile_config):
    config = load_config(fixture_profile_config)
    watcher = _new_watcher(config.profile_name)
    assert isinstance(watcher, _WatcherThread)
    assert watcher._mode == "poll"


def test_new_watcher_watchdog_mode(fixture_profile_config, monkeypatch):
    from packages.kb.indexer import profile_ops

    config = load_config(fixture_profile_config)
    profile_ops.save_watch_settings(config.profile_name, mode="watchdog")
    watcher = _new_watcher(config.profile_name)
    assert isinstance(watcher, _WatchdogThread)
    profile_ops.save_watch_settings(config.profile_name, mode="poll")
