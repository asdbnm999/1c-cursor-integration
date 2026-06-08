from packages.kb.indexer.progress import IndexProgress


def test_progress_update_file():
    p = IndexProgress()
    p.update_file(5, "/proj/Documents/Doc/Module.bsl", 100)
    d = p.to_dict()
    assert d["current_file"] == 5
    assert d["total_files"] == 100
    assert d["percent"] == 5.0
    assert "Module.bsl" in d["message"]
    assert "5/100" in d["message"]


def test_progress_chunks_estimate_extrapolates():
    p = IndexProgress()
    p.total_files = 3082
    p.update_chunks_stats(produced=14603, written=14603, files_done=2639)
    assert p.chunks_estimated >= 14603
    assert p.chunks_estimated > 9246


def test_progress_chunks_estimate_grows_with_files():
    p = IndexProgress()
    p.total_files = 100
    p.update_chunks_stats(produced=50, written=40, files_done=10)
    assert p.chunks_estimated == 500
    p.update_chunks_stats(produced=120, written=100, files_done=20)
    assert p.chunks_estimated == 600
