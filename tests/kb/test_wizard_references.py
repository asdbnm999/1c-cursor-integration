from pathlib import Path

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.exceptions import WizardError
from packages.kb.indexer.references import find_references
from packages.kb.indexer.object_modules import list_object_modules
from packages.kb.indexer.wizard import detect_format, estimate_index_time, run_wizard, scan_preview


def test_detect_xml_export(xml_export_tree: Path):
    assert detect_format(xml_export_tree) == "xml_export"


def test_wizard_preview(xml_export_tree: Path):
    preview = scan_preview(xml_export_tree, "xml_export")
    assert preview["metadata_files"] >= 1
    assert preview["bsl_files"] >= 1
    est = estimate_index_time(preview)
    assert est["seconds_estimated"] >= 30
    assert "human" in est


def test_run_wizard(xml_export_tree: Path):
    result = run_wizard(xml_export_tree)
    assert result["detected_format"] == "xml_export"
    assert result["preview"]["total_indexable"] >= 2


def test_wizard_missing_dir(tmp_path: Path):
    with pytest.raises(WizardError):
        run_wizard(tmp_path / "missing")


def test_find_references(fixture_profile_config, xml_export_tree: Path):
    config = load_config(fixture_profile_config)
    refs = find_references(config, "Проведение")
    assert len(refs) >= 1
    assert any("ObjectModule.bsl" in r["relative_path"] for r in refs)


def test_list_object_modules(fixture_profile_config):
    config = load_config(fixture_profile_config)
    modules = list_object_modules(config, "Document", "ТестовыйДокумент")
    assert len(modules) >= 1
    assert any(m["name"] == "ObjectModule.bsl" for m in modules)
