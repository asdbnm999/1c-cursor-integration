import shutil
from pathlib import Path

import pytest

from packages.kb.indexer.bsl_compare import compare_bsl_modules
from packages.kb.indexer.config import load_config
from packages.kb.indexer.profile_ops import clone_profile, delete_profile


def test_bsl_compare_identical(fixture_profile_config):
    config = load_config(fixture_profile_config)
    target = "test-fixture-bsl-a"
    try:
        clone_profile(config.profile_name, target, display_name="BSL A")
        result = compare_bsl_modules(config.profile_name, target)
        assert result["summary"]["changed_count"] == 0
        assert result["summary"]["bsl_files_a"] >= 1
    finally:
        delete_profile(target)


def test_bsl_compare_detects_change(
    fixture_profile_config,
    xml_export_tree: Path,
    tmp_path: Path,
):
    config = load_config(fixture_profile_config)
    target = "test-fixture-bsl-b"
    tree_b = tmp_path / "project_b"
    shutil.copytree(xml_export_tree, tree_b)
    bsl = tree_b / "Documents" / "ТестовыйДокумент" / "Ext" / "ObjectModule.bsl"
    bsl.write_text(bsl.read_text(encoding="utf-8") + "\n// changed line\n", encoding="utf-8")
    try:
        clone_profile(
            config.profile_name,
            target,
            display_name="BSL B",
            root=tree_b,
        )
        result = compare_bsl_modules(config.profile_name, target)
        assert result["summary"]["changed_count"] == 1
        assert result["changed"][0]["lines_added"] >= 1
        assert "changed line" in result["changed"][0]["diff_preview"]
    finally:
        delete_profile(target)
