import json
import tarfile
import tempfile
from pathlib import Path

import pytest
import yaml

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import ArchiveError
from packages.kb.indexer.index_archive import export_index, import_index
from packages.kb.indexer.pipeline import run_index
from packages.kb.indexer.store import count_chunks, reset_store_cache


def test_export_import_roundtrip(fixture_profile_config, tmp_path: Path):
    config = load_config(fixture_profile_config)
    reset_store_cache()
    stats = run_index(config, full=True)
    assert stats["chunks_written"] >= 1

    out = tmp_path / "backup.tar.gz"
    path = export_index(config.profile_name, out)
    assert path.exists()

    reset_store_cache()
    imported = import_index(path, target_profile="imported-fixture", overwrite=True)
    assert imported == "imported-fixture"

    new_config = load_config("imported-fixture")
    assert count_chunks(new_config) >= 1
    assert new_config.store.collection == config.store.collection
    assert new_config.mcp.server_name == "1c-kb-imported-fixture"
    assert new_config.docker.compose_dir == ""

    # cleanup imported profile
    from packages.kb.indexer.profile_ops import delete_profile
    delete_profile("imported-fixture")


def test_import_missing_file(tmp_path: Path):
    with pytest.raises(ArchiveError):
        import_index(tmp_path / "nope.tar.gz")


def test_import_overwrite_conflict(fixture_profile_config, tmp_path: Path):
    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)
    out = tmp_path / "backup.tar.gz"
    export_index(config.profile_name, out)

    with pytest.raises(ArchiveError, match="уже существует"):
        import_index(out, target_profile=config.profile_name, overwrite=False)


def test_import_uncompressed_tar(fixture_profile_config, tmp_path: Path):
    """Браузер/macOS иногда сохраняют экспорт как .tar без gzip."""
    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)
    gz_path = tmp_path / "backup.tar.gz"
    export_index(config.profile_name, gz_path)

    tar_path = tmp_path / "backup.tar"
    with tarfile.open(gz_path, "r:gz") as src, tarfile.open(tar_path, "w") as dest:
        for member in src.getmembers():
            dest.addfile(member, src.extractfile(member))

    reset_store_cache()
    imported = import_index(tar_path, target_profile="imported-tar-only", overwrite=True)
    assert imported == "imported-tar-only"

    from packages.kb.indexer.profile_ops import delete_profile

    delete_profile("imported-tar-only")


def test_import_corrupt_tar(tmp_path: Path):
    bad = tmp_path / "bad.tar.gz"
    bad.write_bytes(b"not a tar archive")
    with pytest.raises(ArchiveError):
        import_index(bad)


def test_repair_imported_profile_identity(fixture_profile_config):
    from packages.kb.indexer.index_archive import repair_imported_profile_identity

    config = load_config(fixture_profile_config)
    config_path = Path(config.config_path)
    original_text = config_path.read_text(encoding="utf-8")
    try:
        raw = yaml.safe_load(original_text)
        raw.setdefault("mcp", {})["server_name"] = "1c-kb-old-name"
        raw.setdefault("docker", {})["compose_dir"] = str(Path.home() / "DockerMCP" / "1c-kb-old-name")
        config_path.write_text(yaml.dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")

        assert repair_imported_profile_identity(config.profile_name) is True
        repaired = load_config(config.profile_name)
        assert repaired.mcp.server_name == f"1c-kb-{config.profile_name}"
        assert repaired.docker.compose_dir == ""
    finally:
        config_path.write_text(original_text, encoding="utf-8")


def test_export_has_schema_version(fixture_profile_config, tmp_path: Path):
    import json
    import tarfile

    config = load_config(fixture_profile_config)
    reset_store_cache()
    run_index(config, full=True)
    out = tmp_path / "backup.tar.gz"
    export_index(config.profile_name, out)

    with tarfile.open(out, "r:gz") as tar:
        for member in tar.getmembers():
            if member.name.endswith("archive-meta.json"):
                meta = json.loads(tar.extractfile(member).read().decode("utf-8"))
                assert meta.get("schema_version") == 1
                assert "embeddings" in meta
                break
        else:
            pytest.fail("archive-meta.json not found")
