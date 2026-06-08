from pathlib import Path

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.profile_ops import create_profile, delete_profile_completely
from packages.kb.indexer.profiles import PROJECT_ROOT


def test_delete_profile_completely_removes_data(xml_export_tree: Path):
    name = "delete-complete-test"
    create_profile(
        name=name,
        display_name="Delete Test",
        fmt="xml_export",
        root=xml_export_tree,
        docs_enabled=False,
    )
    data_dir = PROJECT_ROOT / "data" / "profiles" / name
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "marker.txt").write_text("x", encoding="utf-8")

    result = delete_profile_completely(name)
    assert result["profile_config"] is True
    assert result["data_dir"] is True
    assert not (PROJECT_ROOT / "profiles" / name).exists()
    assert not data_dir.exists()
