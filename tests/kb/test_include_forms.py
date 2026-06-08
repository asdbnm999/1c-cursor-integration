from pathlib import Path

import pytest

from packages.kb.indexer.config import load_config
from packages.kb.indexer.models import FileKind
from packages.kb.indexer.profile_ops import create_profile, delete_profile
from packages.kb.indexer.scanner import scan_profile


@pytest.fixture
def edt_with_forms(tmp_path: Path) -> Path:
    src = tmp_path / "src"
    doc = src / "Documents" / "ТестовыйДокумент"
    doc.mkdir(parents=True)
    (doc / "ТестовыйДокумент.mdo").write_text(
        '<?xml version="1.0"?><mdclass:Document xmlns:mdclass="http://g5.1c.ru/v8/dt/metadata/mdclass">'
        "<name>ТестовыйДокумент</name></mdclass:Document>",
        encoding="utf-8",
    )
    form_dir = doc / "Forms" / "ФормаДокумента"
    form_dir.mkdir(parents=True)
    (form_dir / "Form.form").write_text(
        '<?xml version="1.0"?><form:Form xmlns:form="http://g5.1c.ru/v8/dt/form">'
        "<name>ФормаДокумента</name></form:Form>",
        encoding="utf-8",
    )
    (form_dir / "Module.bsl").write_text("Процедура ПриОткрытии()\nКонецПроцедуры\n", encoding="utf-8")
    common = src / "CommonForms" / "ОбщаяФорма"
    common.mkdir(parents=True)
    (common / "Form.form").write_text(
        '<?xml version="1.0"?><form:Form xmlns:form="http://g5.1c.ru/v8/dt/form">'
        "<name>ОбщаяФорма</name></form:Form>",
        encoding="utf-8",
    )
    (common / "Module.bsl").write_text("Процедура Общая()\nКонецПроцедуры\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def xml_with_forms(tmp_path: Path) -> Path:
    doc = tmp_path / "Documents" / "ТестовыйДокумент"
    doc.mkdir(parents=True)
    (doc / "ТестовыйДокумент.xml").write_text(
        '<?xml version="1.0"?><MetaDataObject></MetaDataObject>',
        encoding="utf-8",
    )
    forms = doc / "Forms" / "ФормаДокумента"
    forms.mkdir(parents=True)
    (forms / "ФормаДокумента.xml").write_text(
        '<?xml version="1.0"?><Form></Form>',
        encoding="utf-8",
    )
    ext = forms / "Ext" / "Form"
    ext.mkdir(parents=True)
    (ext / "Module.bsl").write_text("Процедура ПриОткрытии()\nКонецПроцедуры\n", encoding="utf-8")
    (forms / "Ext" / "FormModule.bsl").write_text(
        "Процедура ОбработкаКоманды()\nКонецПроцедуры\n",
        encoding="utf-8",
    )
    return tmp_path


def test_forms_excluded_by_default(xml_with_forms: Path, tmp_path: Path):
    profile_name = "forms-off-test"
    try:
        create_profile(
            name=profile_name,
            display_name="Forms Off",
            fmt="xml_export",
            root=xml_with_forms,
            docs_enabled=False,
            include_forms=False,
        )
        config = load_config(profile_name)
        entries = scan_profile(config)
        form_bsl = [e for e in entries if e.kind == FileKind.BSL and "Forms" in e.relative_path]
        form_meta = [e for e in entries if e.kind == FileKind.METADATA and "Forms" in e.relative_path]
        assert len(form_bsl) == 0
        assert len(form_meta) == 0
    finally:
        delete_profile(profile_name)


def test_forms_included_when_enabled(xml_with_forms: Path):
    profile_name = "forms-on-test"
    try:
        create_profile(
            name=profile_name,
            display_name="Forms On",
            fmt="xml_export",
            root=xml_with_forms,
            docs_enabled=False,
            include_forms=True,
        )
        config = load_config(profile_name)
        entries = scan_profile(config)
        form_bsl = [e for e in entries if e.kind == FileKind.BSL and "Forms" in e.relative_path]
        form_meta = [e for e in entries if e.kind == FileKind.METADATA and "Forms" in e.relative_path]
        assert len(form_bsl) >= 1
        assert len(form_meta) >= 1
    finally:
        delete_profile(profile_name)


def test_edt_forms_excluded_by_default(edt_with_forms: Path):
    profile_name = "edt-forms-off"
    try:
        create_profile(
            name=profile_name,
            display_name="EDT Off",
            fmt="edt",
            root=edt_with_forms,
            docs_enabled=False,
            include_forms=False,
        )
        config = load_config(profile_name)
        entries = scan_profile(config)
        form_meta = [e for e in entries if e.relative_path.endswith("Form.form")]
        form_bsl = [
            e for e in entries
            if e.kind == FileKind.BSL
            and ("Forms" in e.relative_path or "CommonForms" in e.relative_path)
        ]
        assert len(form_meta) == 0
        assert len(form_bsl) == 0
    finally:
        delete_profile(profile_name)


def test_edt_forms_included_when_enabled(edt_with_forms: Path):
    profile_name = "edt-forms-on"
    try:
        create_profile(
            name=profile_name,
            display_name="EDT On",
            fmt="edt",
            root=edt_with_forms,
            docs_enabled=False,
            include_forms=True,
        )
        config = load_config(profile_name)
        entries = scan_profile(config)
        form_meta = [e for e in entries if e.relative_path.endswith("Form.form")]
        form_bsl = [
            e for e in entries
            if e.kind == FileKind.BSL
            and ("Forms" in e.relative_path or "CommonForms" in e.relative_path)
        ]
        assert len(form_meta) == 2
        assert len(form_bsl) == 2
    finally:
        delete_profile(profile_name)


def test_edt_form_metadata_extract(edt_with_forms: Path):
    from packages.kb.indexer.extract_metadata import extract_metadata
    from packages.kb.indexer.models import SourceFormat

    profile_name = "edt-forms-meta"
    try:
        create_profile(
            name=profile_name,
            display_name="EDT Meta",
            fmt="edt",
            root=edt_with_forms,
            include_forms=True,
            docs_enabled=False,
        )
        config = load_config(profile_name)
        form_entry = next(
            e for e in scan_profile(config) if e.relative_path.endswith("Form.form")
        )
        obj = extract_metadata(form_entry.path, config.profile_name, SourceFormat.EDT)
        assert obj.object_type == "Form"
        assert "ТестовыйДокумент" in obj.comment or "ОбщаяФорма" in obj.name
    finally:
        delete_profile(profile_name)


def test_edt_wizard_counts_forms(edt_with_forms: Path):
    from packages.kb.indexer.wizard import detect_format, scan_preview

    assert detect_format(edt_with_forms) == "edt"
    preview = scan_preview(edt_with_forms, "edt")
    assert preview["form_modules"] >= 2
    assert preview["metadata_files"] >= 1
