from __future__ import annotations

import os
from functools import lru_cache

import httpx

from packages.kb.indexer.config import EmbeddingsConfig
from packages.kb.indexer.exceptions import EmbeddingError

_model = None
_model_key: str | None = None

# Размерности без пробного embed (ускоряет health и импорт архива).
KNOWN_LOCAL_DIMS: dict[str, int] = {
    "intfloat/multilingual-e5-small": 384,
    "intfloat/multilingual-e5-base": 768,
    "intfloat/multilingual-e5-large": 1024,
}


def _resolve_device(device: str) -> str:
    if device and device != "auto":
        return device
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _get_local_model(model_name: str, device: str):
    global _model, _model_key
    resolved = _resolve_device(device)
    key = f"{model_name}::{resolved}"
    if _model is None or _model_key != key:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(model_name, device=resolved)
        _model_key = key
    return _model


def clear_model_cache() -> None:
    global _model, _model_key
    _model = None
    _model_key = None


def _local_model_cached(model_name: str) -> bool:
    """Веса модели уже в локальном кэше Hugging Face (без сети)."""
    global _model, _model_key
    if _model is not None and _model_key and _model_key.startswith(f"{model_name}::"):
        return True
    try:
        from huggingface_hub import try_to_load_from_cache

        for filename in ("model.safetensors", "pytorch_model.bin"):
            if try_to_load_from_cache(model_name, filename) is not None:
                return True
    except Exception:
        pass
    return False


def embed_texts(texts: list[str], config: EmbeddingsConfig) -> list[list[float]]:
    if not texts:
        return []
    try:
        if config.provider == "openai":
            return _embed_openai(texts, config)
        prefixed = [f"passage: {t}" for t in texts]
        model = _get_local_model(config.model, config.device)
        vectors = model.encode(prefixed, normalize_embeddings=True)
        return vectors.tolist()
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError("Не удалось построить эмбеддинги", details=str(exc)) from exc


def embed_query(query: str, config: EmbeddingsConfig) -> list[float]:
    try:
        if config.provider == "openai":
            return _embed_openai([f"query: {query}"], config)[0]
        model = _get_local_model(config.model, config.device)
        vector = model.encode([f"query: {query}"], normalize_embeddings=True)
        return vector[0].tolist()
    except EmbeddingError:
        raise
    except Exception as exc:
        raise EmbeddingError("Не удалось построить эмбеддинг запроса", details=str(exc)) from exc


def _embed_openai(texts: list[str], config: EmbeddingsConfig) -> list[list[float]]:
    api_key = os.getenv(config.openai_api_key_env, "")
    if not api_key:
        raise EmbeddingError(
            "Не задан ключ OpenAI",
            details=config.openai_api_key_env,
        )
    try:
        response = httpx.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": config.openai_model, "input": texts},
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [item["embedding"] for item in sorted(data, key=lambda x: x["index"])]
    except httpx.HTTPError as exc:
        raise EmbeddingError("Ошибка API OpenAI", details=str(exc)) from exc


def get_embedding_dimension(config: EmbeddingsConfig) -> int:
    """Размерность вектора для текущей модели."""
    if config.provider == "openai":
        dims = {
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "text-embedding-ada-002": 1536,
        }
        return dims.get(config.openai_model, 1536)
    if config.model in KNOWN_LOCAL_DIMS:
        return KNOWN_LOCAL_DIMS[config.model]
    vector = embed_query("dimension probe", config)
    return len(vector)


def check_embeddings(config: EmbeddingsConfig, *, load_model: bool = False) -> dict:
    """Проверка embeddings.

    По умолчанию (load_model=False) не тянет веса с Hugging Face — только import/cached.
    Полная загрузка — для мастера и явной кнопки «Проверить модель».
    """
    if config.provider == "openai":
        key = os.getenv(config.openai_api_key_env, "")
        return {
            "ok": bool(key),
            "provider": "openai",
            "model": config.openai_model,
            "device": "api",
            "message": "OK" if key else f"Нет переменной {config.openai_api_key_env}",
        }

    device = _resolve_device(config.device)
    base = {
        "provider": "local",
        "model": config.model,
        "device": device,
    }

    try:
        import sentence_transformers  # noqa: F401
    except Exception as exc:
        return {
            **base,
            "ok": False,
            "cached": False,
            "message": f"Пакет sentence-transformers недоступен: {exc}",
        }

    if load_model:
        try:
            _get_local_model(config.model, config.device)
            return {
                **base,
                "ok": True,
                "cached": True,
                "loaded": True,
                "message": f"Модель загружена на {device}",
            }
        except Exception as exc:
            return {
                **base,
                "ok": False,
                "cached": False,
                "message": str(exc),
            }

    cached = _local_model_cached(config.model)
    if cached:
        return {
            **base,
            "ok": True,
            "cached": True,
            "loaded": _model is not None,
            "message": f"Модель в кэше ({device})",
        }

    return {
        **base,
        "ok": True,
        "cached": False,
        "loaded": False,
        "message": "Модель будет загружена при первой индексации",
    }
