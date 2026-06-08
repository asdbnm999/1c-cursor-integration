from pathlib import Path

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import CompareError
from packages.kb.indexer.profile_compare import compare_profiles
from packages.kb.indexer.profile_ops import clone_profile, delete_profile


def test_compare_same_profile_raises(fixture_profile_config):
    config = load_config(fixture_profile_config)
    with pytest.raises(CompareError):
        compare_profiles(config.profile_name, config.profile_name)


def test_clone_and_compare(fixture_profile_config):
    config = load_config(fixture_profile_config)
    target = "test-fixture-clone"
    try:
        clone_profile(config.profile_name, target, display_name="Clone")
        result = compare_profiles(config.profile_name, target)
        assert result["summary"]["objects_a"] == result["summary"]["objects_b"]
        assert result["summary"]["changed_count"] == 0
        assert "bsl" in result
        assert result["summary"]["bsl_changed_count"] == 0
    finally:
        delete_profile(target)
