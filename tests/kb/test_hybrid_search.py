from unittest.mock import MagicMock, patch

from packages.kb.indexer.hybrid_search import hybrid_search, tokenize


def test_tokenize_russian():
    tokens = tokenize("Документ Проведение регистра")
    assert "документ" in tokens
    assert "проведение" in tokens


def test_hybrid_search_empty_vector(monkeypatch, fixture_profile_config):
    from packages.kb.indexer.config import load_config

    config = load_config(fixture_profile_config)

    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [[]],
        "metadatas": [[]],
        "distances": [[]],
        "ids": [[]],
    }
    mock_collection.get.return_value = {"documents": [], "metadatas": [], "ids": []}

    with patch("packages.kb.indexer.hybrid_search.embed_query", return_value=[0.1] * 8):
        with patch("packages.kb.indexer.hybrid_search.query_chunks", return_value=mock_collection.query.return_value):
            with patch("packages.kb.indexer.hybrid_search.get_collection", return_value=mock_collection):
                hits = hybrid_search(config, "тест", limit=5)
    assert isinstance(hits, list)
