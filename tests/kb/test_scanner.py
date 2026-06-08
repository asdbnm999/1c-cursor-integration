from packages.kb.indexer.config import load_config
from packages.kb.indexer.models import FileKind
from packages.kb.indexer.scanner import scan_profile


def test_scan_xml_export_fixture(fixture_profile_config):
    config = load_config(fixture_profile_config)
    entries = scan_profile(config)
    kinds = {e.kind for e in entries}
    assert FileKind.METADATA in kinds
    assert FileKind.BSL in kinds
    metadata_paths = [e.relative_path for e in entries if e.kind == FileKind.METADATA]
    assert "Documents/ТестовыйДокумент.xml" in metadata_paths
    assert FileKind.MARKDOWN not in kinds
