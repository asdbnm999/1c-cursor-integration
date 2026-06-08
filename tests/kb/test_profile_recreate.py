from pathlib import Path

from packages.kb.indexer.config import load_config
from packages.kb.indexer.profile_ops import create_profile, delete_profile_completely
from packages.kb.indexer.profiles import PROJECT_ROOT
from packages.kb.indexer.store import count_chunks


def test_recreate_profile_clears_orphan_index_data(xml_export_tree: Path):
    name = "recreate-test"
    try:
        delete_profile_completely(name)
    except Exception:
        pass
    create_profile(
        name=name,
        display_name="Recreate",
        fmt="xml_export",
        root=xml_export_tree,
        docs_enabled=False,
    )
    delete_profile_completely(name)
    assert not (PROJECT_ROOT / "data" / "profiles" / name).exists()

    data_dir = PROJECT_ROOT / "data" / "profiles" / name
    data_dir.mkdir(parents=True)
    chroma = data_dir / "chroma"
    chroma.mkdir()
    (chroma / "stale.bin").write_bytes(b"old")
    (data_dir / "last-job.json").write_text('{"status": "completed"}', encoding="utf-8")

    create_profile(
        name=name,
        display_name="Recreate",
        fmt="xml_export",
        root=xml_export_tree,
        docs_enabled=False,
    )
    config = load_config(name)
    assert not (data_dir / "chroma" / "stale.bin").exists()
    assert not (data_dir / "last-job.json").exists()
    assert count_chunks(config) == 0
