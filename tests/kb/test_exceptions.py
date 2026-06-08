from packages.kb.indexer.exceptions import (
    ArchiveError,
    CompareError,
    EmbeddingError,
    IndexEmptyError,
    IndexerError,
    ProfileNotFoundError,
    SourceNotFoundError,
)


def test_exception_hierarchy():
    assert issubclass(ProfileNotFoundError, IndexerError)
    assert issubclass(IndexEmptyError, IndexerError)
    assert issubclass(EmbeddingError, IndexerError)
    assert issubclass(ArchiveError, IndexerError)
    assert issubclass(CompareError, IndexerError)


def test_exception_details():
    err = SourceNotFoundError("Каталог не найден", details="/tmp/x")
    assert "/tmp/x" in str(err)
    assert err.details == "/tmp/x"
