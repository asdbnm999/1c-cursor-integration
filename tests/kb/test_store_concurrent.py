"""Проверка единственного клиента Chroma при параллельном count во время upsert."""

from __future__ import annotations

import threading
import time

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.models import Chunk
from packages.kb.indexer.store import (
    count_chunks,
    reset_collection_store,
    reset_store_cache,
    upsert_chunks,
)


@pytest.fixture(autouse=True)
def _clean_store(fixture_profile_config):
    config = load_config(fixture_profile_config)
    reset_store_cache()
    reset_collection_store(config)
    yield
    reset_store_cache()


def test_concurrent_count_during_upsert(fixture_profile_config):
    config = load_config(fixture_profile_config)
    dim = 384
    chunk = Chunk(
        id="concurrent-test",
        text="sample",
        metadata={"path": "/tmp/concurrent.bsl"},
        embedding=[0.01] * dim,
    )
    stop = threading.Event()
    errors: list[str] = []

    def poll_counts():
        while not stop.is_set():
            try:
                count_chunks(config)
            except Exception as exc:
                errors.append(str(exc))
            time.sleep(0.01)

    worker = threading.Thread(target=poll_counts, daemon=True)
    worker.start()
    try:
        upsert_chunks(config, [chunk])
    finally:
        stop.set()
        worker.join(timeout=2)

    assert not errors
    assert count_chunks(config, force=True) == 1


def test_reset_store_while_counting(fixture_profile_config):
    config = load_config(fixture_profile_config)
    dim = 384
    chunk = Chunk(
        id="reset-race",
        text="sample",
        metadata={"path": "/tmp/reset-race.bsl"},
        embedding=[0.01] * dim,
    )
    upsert_chunks(config, [chunk])
    stop = threading.Event()

    def poll_counts():
        while not stop.is_set():
            count_chunks(config, force=True)
            time.sleep(0.001)

    worker = threading.Thread(target=poll_counts, daemon=True)
    worker.start()
    try:
        for _ in range(3):
            reset_collection_store(config)
            time.sleep(0.02)
    finally:
        stop.set()
        worker.join(timeout=2)

    assert count_chunks(config, force=True) == 0
