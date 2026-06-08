from packages.kb.indexer.config import load_config
from packages.kb.indexer.pipeline import run_index
from packages.kb.indexer.profile_ops import clone_profile, delete_profile
from packages.kb.indexer.store import count_chunks, reset_store_cache


def test_clone_copy_index(fixture_profile_config):
    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)

    target = "test-fixture-copy-idx"
    try:
        clone_profile(config.profile_name, target, copy_index=True)
        reset_store_cache()
        cloned = load_config(target)
        assert count_chunks(cloned) == count_chunks(config)
        assert cloned.store.collection == config.store.collection
    finally:
        delete_profile(target)
