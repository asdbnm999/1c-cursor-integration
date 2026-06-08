from pathlib import Path

from packages.kb.indexer.extract_metadata import extract_metadata
from packages.kb.indexer.models import SourceFormat

FIXTURE_XML = Path(__file__).parent / "fixtures" / "xml_document.xml"


def test_xml_export_document_metadata():
    obj = extract_metadata(str(FIXTURE_XML), "test", SourceFormat.XML_EXPORT)
    assert obj.object_type == "Document"
    assert obj.name == "ТестовыйДокумент"
    assert "документ" in obj.synonym.lower()
    assert any(a["name"] == "Сумма" for a in obj.attributes)
    assert any("ТестовыйРегистр" in r for r in obj.register_records)
