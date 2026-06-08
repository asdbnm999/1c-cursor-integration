from packages.kb.indexer.chunkers import chunk_metadata, content_hash
from packages.kb.indexer.config import load_config
from packages.kb.indexer.models import MetadataObject, SourceFormat


def test_content_hash_stable():
    h1 = content_hash("metadata", "/a/b.xml", "Doc", "text")
    h2 = content_hash("metadata", "/a/b.xml", "Doc", "text")
    assert h1 == h2


def test_chunk_metadata_prefix(fixture_profile_config):
    config = load_config(fixture_profile_config)
    obj = MetadataObject(
        object_type="Document",
        name="ТестовыйДокумент",
        synonym="Тестовый документ",
        path="/tmp/doc.xml",
        source_name=config.profile_name,
        source_format=SourceFormat.XML_EXPORT,
        attributes=[{"name": "Сумма", "type": "xs:decimal"}],
        register_records=["AccumulationRegister.ТестовыйРегистр"],
    )
    chunks = chunk_metadata(config, obj)
    assert len(chunks) == 1
    assert "ТестовыйДокумент" in chunks[0].text
    assert "Сумма" in chunks[0].text
