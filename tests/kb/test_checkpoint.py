from packages.kb.indexer.checkpoint import clear_checkpoint, load_checkpoint, save_checkpoint
from packages.kb.indexer.config import load_config


def test_checkpoint_roundtrip(fixture_profile_config):
    config = load_config(fixture_profile_config)
    clear_checkpoint(config)
    save_checkpoint(
        config,
        processed_paths=["/a/one.bsl", "/a/two.bsl"],
        phase="chunking",
        full=True,
    )
    loaded = load_checkpoint(config)
    assert loaded is not None
    assert loaded["processed_count"] == 2
    assert loaded["phase"] == "chunking"
    clear_checkpoint(config)
    assert load_checkpoint(config) is None
