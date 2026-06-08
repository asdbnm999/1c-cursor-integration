from __future__ import annotations

import fnmatch
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.exceptions import SourceNotFoundError
from packages.kb.indexer.constants import BSL_MODULE_NAMES, FORM_XML_SKIP_NAMES, FOLDER_TO_OBJECT_TYPE
from packages.kb.indexer.models import FileEntry, FileKind, SourceFormat


def _matches_glob(path: Path, patterns: list[str]) -> bool:
    posix = path.as_posix()
    return any(fnmatch.fnmatch(posix, pattern) for pattern in patterns)


def _is_excluded(path: Path, base: Path, config: ProfileConfig) -> bool:
    rel = path.relative_to(base)
    parts = rel.parts
    indexing = config.indexing

    if indexing.exclude_dirs and parts:
        if parts[0] in indexing.exclude_dirs:
            return True
        if any(part in indexing.exclude_dirs for part in parts):
            return True

    if indexing.exclude_globs and _matches_glob(rel, indexing.exclude_globs):
        if config.indexing.include_forms:
            if path.suffix.lower() == ".bsl" and "Forms" in rel.parts:
                pass
            elif path.suffix.lower() == ".form":
                pass
            elif path.suffix.lower() == ".xml" and "Forms" in rel.parts:
                pass
            else:
                return True
        else:
            return True

    if not config.indexing.include_forms and "Forms" in rel.parts:
        if config.format == "xml_export" and path.suffix.lower() in {".bsl", ".xml"}:
            return True
        if config.format == "edt" and path.suffix.lower() in {".bsl", ".form", ".mdo"}:
            return True

    if (
        not config.indexing.include_forms
        and config.format == "edt"
        and rel.parts[0] == "CommonForms"
        and path.suffix.lower() in {".bsl", ".form", ".mdo"}
    ):
        return True

    return False


def _is_included_dir(rel: Path, config: ProfileConfig) -> bool:
    indexing = config.indexing
    if not indexing.include_dirs:
        return True
    if not rel.parts:
        return True
    return rel.parts[0] in indexing.include_dirs


def _scan_edt_metadata(base: Path, config: ProfileConfig) -> list[FileEntry]:
    entries: list[FileEntry] = []
    fmt = SourceFormat.EDT
    for mdo in base.rglob("*.mdo"):
        if not mdo.is_file():
            continue
        rel = mdo.relative_to(base)
        if not _is_included_dir(rel.parent, config):
            continue
        if _is_excluded(mdo, base, config):
            continue
        if config.indexing.include_forms and "Forms" in rel.parts:
            continue
        entries.append(
            FileEntry(
                path=str(mdo),
                kind=FileKind.METADATA,
                source_name=config.profile_name,
                source_format=fmt,
                relative_path=rel.as_posix(),
            )
        )

    if config.indexing.include_forms:
        for form_path in base.rglob("*.form"):
            if not form_path.is_file():
                continue
            rel = form_path.relative_to(base)
            if not _is_included_dir(rel.parent, config):
                continue
            if _is_excluded(form_path, base, config):
                continue
            if not _is_edt_form_metadata(rel):
                continue
            entries.append(
                FileEntry(
                    path=str(form_path),
                    kind=FileKind.METADATA,
                    source_name=config.profile_name,
                    source_format=fmt,
                    relative_path=rel.as_posix(),
                )
            )
    return entries


def _is_edt_form_metadata(rel: Path) -> bool:
    """EDT: Documents/Obj/Forms/FormName/Form.form или CommonForms/Name/Form.form."""
    if rel.suffix.lower() != ".form":
        return False
    if rel.name != "Form.form":
        return False
    if rel.parts[0] == "CommonForms" and len(rel.parts) >= 2:
        return True
    if rel.parts[0] not in FOLDER_TO_OBJECT_TYPE:
        return False
    try:
        forms_idx = rel.parts.index("Forms")
    except ValueError:
        return False
    return forms_idx >= 2 and len(rel.parts) >= forms_idx + 2


def _is_xml_form_metadata(rel: Path) -> bool:
    if "Forms" not in rel.parts or rel.suffix.lower() != ".xml":
        return False
    if rel.name in FORM_XML_SKIP_NAMES:
        return False
    if rel.parts[0] not in FOLDER_TO_OBJECT_TYPE:
        return False
    try:
        forms_idx = rel.parts.index("Forms")
    except ValueError:
        return False
    return forms_idx >= 2 and len(rel.parts) >= forms_idx + 2


def _is_xml_export_metadata(path: Path, base: Path, *, include_forms: bool = False) -> bool:
    rel = path.relative_to(base)
    if rel.name == "Configuration.xml" and len(rel.parts) == 1:
        return True
    if len(rel.parts) == 2:
        folder, filename = rel.parts
        if folder in FOLDER_TO_OBJECT_TYPE:
            return filename.endswith(".xml")
    if include_forms and _is_xml_form_metadata(rel):
        return True
    return False


def _scan_xml_metadata(base: Path, config: ProfileConfig) -> list[FileEntry]:
    entries: list[FileEntry] = []
    fmt = SourceFormat.XML_EXPORT
    for xml in base.rglob("*.xml"):
        if not xml.is_file():
            continue
        rel = xml.relative_to(base)
        if not _is_included_dir(rel.parent, config):
            continue
        if _is_excluded(xml, base, config):
            continue
        if not _is_xml_export_metadata(xml, base, include_forms=config.indexing.include_forms):
            continue
        entries.append(
            FileEntry(
                path=str(xml),
                kind=FileKind.METADATA,
                source_name=config.profile_name,
                source_format=fmt,
                relative_path=rel.as_posix(),
            )
        )
    return entries


def _scan_bsl(base: Path, config: ProfileConfig, fmt: SourceFormat) -> list[FileEntry]:
    entries: list[FileEntry] = []
    for bsl in base.rglob("*.bsl"):
        if not bsl.is_file():
            continue
        rel = bsl.relative_to(base)
        if not _is_included_dir(rel.parent, config):
            continue
        if _is_excluded(bsl, base, config):
            continue
        if bsl.name not in BSL_MODULE_NAMES:
            continue
        entries.append(
            FileEntry(
                path=str(bsl),
                kind=FileKind.BSL,
                source_name=config.profile_name,
                source_format=fmt,
                relative_path=rel.as_posix(),
            )
        )
    return entries


def _scan_docs(config: ProfileConfig) -> list[FileEntry]:
    entries: list[FileEntry] = []
    if not config.docs.enabled or not config.docs.paths:
        return entries

    fmt = SourceFormat.EDT if config.format == "edt" else SourceFormat.XML_EXPORT
    for docs_path in config.docs.paths:
        root = config.root / docs_path
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".md":
            entries.append(
                FileEntry(
                    path=str(root),
                    kind=FileKind.MARKDOWN,
                    source_name=config.profile_name,
                    source_format=fmt,
                    relative_path=root.relative_to(config.root).as_posix(),
                )
            )
            continue
        for md in root.rglob("*.md"):
            if not md.is_file():
                continue
            entries.append(
                FileEntry(
                    path=str(md),
                    kind=FileKind.MARKDOWN,
                    source_name=config.profile_name,
                    source_format=fmt,
                    relative_path=md.relative_to(config.root).as_posix(),
                )
            )
    return entries


def scan_profile(config: ProfileConfig) -> list[FileEntry]:
    base = config.source_base
    if not base.exists():
        raise SourceNotFoundError(
            "Каталог проекта не найден",
            details=str(base),
        )

    entries: list[FileEntry] = []
    if config.format == "edt":
        entries.extend(_scan_edt_metadata(base, config))
        entries.extend(_scan_bsl(base, config, SourceFormat.EDT))
    elif config.format == "xml_export":
        entries.extend(_scan_xml_metadata(base, config))
        entries.extend(_scan_bsl(base, config, SourceFormat.XML_EXPORT))
    else:
        raise ValueError(f"Неизвестный формат: {config.format}. Допустимо: edt, xml_export")

    entries.extend(_scan_docs(config))
    return entries


# Обратная совместимость
def scan_source(source) -> list[FileEntry]:
    return scan_profile(source)
