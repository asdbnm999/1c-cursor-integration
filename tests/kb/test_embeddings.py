from unittest.mock import patch

from packages.kb.indexer.embeddings import check_embeddings, _resolve_device
from packages.kb.indexer.config import EmbeddingsConfig


def test_resolve_device_auto():
    device = _resolve_device("auto")
    assert device in {"cpu", "cuda", "mps"}


def test_check_embeddings_openai_missing_key():
    cfg = EmbeddingsConfig(provider="openai", openai_api_key_env="MISSING_KEY_XYZ")
    result = check_embeddings(cfg)
    assert result["ok"] is False


def test_check_embeddings_local_lightweight_skips_model_load():
    cfg = EmbeddingsConfig(provider="local", model="intfloat/multilingual-e5-small")
    with patch("packages.kb.indexer.embeddings._get_local_model") as load:
        with patch("packages.kb.indexer.embeddings._local_model_cached", return_value=False):
            result = check_embeddings(cfg, load_model=False)
    load.assert_not_called()
    assert result["ok"] is True
    assert result["loaded"] is False


def test_check_embeddings_local_eager_loads_model():
    cfg = EmbeddingsConfig(provider="local", model="intfloat/multilingual-e5-small")
    with patch("packages.kb.indexer.embeddings._get_local_model") as load:
        load.return_value = object()
        result = check_embeddings(cfg, load_model=True)
    load.assert_called_once()
    assert result["ok"] is True
    assert result["loaded"] is True
