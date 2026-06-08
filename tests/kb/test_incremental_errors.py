from unittest.mock import patch

import pytest

from packages.kb.indexer.exceptions import IndexEmptyError
from packages.kb.indexer.incremental import resolve_incremental_paths


def test_resolve_incremental_empty_index(fixture_profile_config):
    from packages.kb.indexer.config import load_config

    config = load_config(fixture_profile_config)
    with patch("packages.kb.indexer.incremental.count_chunks", return_value=0):
        with pytest.raises(IndexEmptyError):
            resolve_incremental_paths(config)
