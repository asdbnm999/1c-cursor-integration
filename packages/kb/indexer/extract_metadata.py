from __future__ import annotations

from pathlib import Path
from typing import Any

from lxml import etree

from packages.kb.indexer.constants import FOLDER_TO_OBJECT_TYPE, XML_ROOT_TO_OBJECT_TYPE
from packages.kb.indexer.models import MetadataObject, SourceFormat


def _local_name(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def _text(node: etree._Element | None) -> str:
    if node is None:
        return ""
    return (node.text or "").strip()


def _synonym_edt(root: etree._Element) -> str:
    for child in root:
        if _local_name(child.tag) == "synonym":
            for item in child:
                if _local_name(item.tag) == "value":
                    return _text(item)
    return ""


def _synonym_xml_export(node: etree._Element) -> str:
    for item in node.iter():
        if _local_name(item.tag) == "content":
            value = _text(item)
            if value:
                return value
    return ""


def _type_from_types_edt(node: etree._Element) -> str:
    for child in node:
        if _local_name(child.tag) == "types":
            return _text(child)
    for child in node:
        if _local_name(child.tag) == "type":
            types = child.find(".//{*}types")
            if types is not None:
                return _text(types)
    return "?"


def _type_from_xml_export(type_node: etree._Element) -> str:
    for part in type_node.iter():
        ln = _local_name(part.tag)
        if ln == "Type" and part is not type_node:
            value = _text(part)
            if value:
                return value
        if ln == "types":
            value = _text(part)
            if value:
                return value
    for part in type_node:
        if _local_name(part.tag) == "Type":
            value = _text(part)
            if value:
                return value
    return "?"


def _attributes_edt(root: etree._Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in root:
        if _local_name(child.tag) != "attributes":
            continue
        name = ""
        synonym = ""
        attr_type = "?"
        for part in child:
            ln = _local_name(part.tag)
            if ln == "name":
                name = _text(part)
            elif ln == "synonym":
                synonym = _synonym_edt(part)
            elif ln == "type":
                attr_type = _type_from_types_edt(part)
        if name:
            result.append({"name": name, "type": attr_type, "synonym": synonym})
    return result


def _attribute_from_xml_node(attr: etree._Element) -> dict[str, Any] | None:
    props = None
    for part in attr:
        if _local_name(part.tag) == "Properties":
            props = part
            break
    if props is None:
        return None
    name = ""
    synonym = ""
    attr_type = "?"
    for part in props:
        ln = _local_name(part.tag)
        if ln == "Name":
            name = _text(part)
        elif ln == "Synonym":
            synonym = _synonym_xml_export(part)
        elif ln == "Type":
            attr_type = _type_from_xml_export(part)
    if not name:
        return None
    return {"name": name, "type": attr_type, "synonym": synonym}


def _attributes_xml_export(obj: etree._Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in obj:
        if _local_name(child.tag) != "ChildObjects":
            continue
        for attr in child:
            if _local_name(attr.tag) != "Attribute":
                continue
            parsed = _attribute_from_xml_node(attr)
            if parsed:
                result.append(parsed)
    return result


def _tabular_sections_edt(root: etree._Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for child in root:
        if _local_name(child.tag) != "tabularSections":
            continue
        name = ""
        attributes: list[dict[str, Any]] = []
        for part in child:
            ln = _local_name(part.tag)
            if ln == "name":
                name = _text(part)
            elif ln == "attributes":
                attr_name = ""
                attr_type = "?"
                for ap in part:
                    aln = _local_name(ap.tag)
                    if aln == "name":
                        attr_name = _text(ap)
                    elif aln == "type":
                        attr_type = _type_from_types_edt(ap)
                if attr_name:
                    attributes.append({"name": attr_name, "type": attr_type})
        if name:
            result.append({"name": name, "attributes": attributes})
    return result


def _tabular_sections_xml_export(obj: etree._Element) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    containers = [obj]
    for child in obj:
        if _local_name(child.tag) == "ChildObjects":
            containers.append(child)
    for container in containers:
        for ts in container:
            if _local_name(ts.tag) != "TabularSection":
                continue
            name = ""
            attributes: list[dict[str, Any]] = []
            for part in ts:
                if _local_name(part.tag) == "Properties":
                    for prop in part:
                        if _local_name(prop.tag) == "Name":
                            name = _text(prop)
                elif _local_name(part.tag) == "ChildObjects":
                    for attr in part:
                        if _local_name(attr.tag) != "Attribute":
                            continue
                        parsed = _attribute_from_xml_node(attr)
                        if parsed:
                            attributes.append(
                                {"name": parsed["name"], "type": parsed.get("type", "?")}
                            )
            if name:
                result.append({"name": name, "attributes": attributes})
    return result


def _register_records_edt(root: etree._Element) -> list[str]:
    records: list[str] = []
    for child in root:
        if _local_name(child.tag) == "registerRecords":
            value = _text(child)
            if value:
                records.append(value)
    return records


def _named_fields_xml_export(
    obj: etree._Element,
    tag_name: str,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    containers = [obj]
    for child in obj:
        if _local_name(child.tag) == "ChildObjects":
            containers.append(child)
    for container in containers:
        for node in container:
            if _local_name(node.tag) != tag_name:
                continue
            parsed = _attribute_from_xml_node(node)
            if parsed:
                result.append(parsed)
    return result


def _register_type_xml_export(obj: etree._Element) -> str:
    for child in obj:
        if _local_name(child.tag) != "Properties":
            continue
        for part in child:
            if _local_name(part.tag) == "RegisterType":
                return _text(part)
    return ""


def _document_posting_xml_export(props: etree._Element | None) -> tuple[str, str]:
    posting = ""
    real_time = ""
    if props is None:
        return posting, real_time
    for part in props:
        ln = _local_name(part.tag)
        if ln == "Posting":
            posting = _text(part)
        elif ln == "RealTimePosting":
            real_time = _text(part)
    return posting, real_time


def _register_records_xml_export(obj: etree._Element) -> list[str]:
    records: list[str] = []
    for child in obj.iter():
        if _local_name(child.tag) != "RegisterRecords":
            continue
        for item in child:
            value = _text(item)
            if value:
                records.append(value)
        if records:
            break
    return records


def _object_type_from_path(path: Path, fmt: SourceFormat) -> tuple[str, str]:
    parts = path.parts
    if fmt == SourceFormat.EDT:
        for idx, part in enumerate(parts):
            if part in FOLDER_TO_OBJECT_TYPE and idx + 1 < len(parts):
                return FOLDER_TO_OBJECT_TYPE[part], parts[idx + 1]
    else:
        if len(parts) >= 2 and parts[-2] in FOLDER_TO_OBJECT_TYPE:
            return FOLDER_TO_OBJECT_TYPE[parts[-2]], path.stem
        if path.name == "Configuration.xml":
            return "Configuration", "Configuration"
    return "Unknown", path.stem


def _parse_edt(path: Path, source_name: str) -> MetadataObject:
    tree = etree.parse(str(path))
    root = tree.getroot()
    object_type, name = _object_type_from_path(path, SourceFormat.EDT)
    if _local_name(root.tag) != object_type and object_type != "Unknown":
        # EDT uses mdclass:Document etc — take name from XML
        for child in root:
            if _local_name(child.tag) == "name":
                name = _text(child)
                break
    else:
        for child in root:
            if _local_name(child.tag) == "name":
                name = _text(child) or name
                break

    version = ""
    comment = ""
    for child in root:
        ln = _local_name(child.tag)
        if ln == "comment":
            comment = _text(child)
        elif ln == "version":
            version = _text(child)

    return MetadataObject(
        object_type=object_type,
        name=name,
        synonym=_synonym_edt(root),
        path=str(path),
        source_name=source_name,
        source_format=SourceFormat.EDT,
        attributes=_attributes_edt(root),
        tabular_sections=_tabular_sections_edt(root),
        register_records=_register_records_edt(root),
        comment=comment,
        version=version,
        raw_xml_summary=etree.tostring(root, encoding="unicode")[:2000],
    )


def _parse_xml_export(path: Path, source_name: str) -> MetadataObject:
    tree = etree.parse(str(path))
    root = tree.getroot()
    obj = None
    object_type = "Unknown"
    for child in root:
        ln = _local_name(child.tag)
        if ln in XML_ROOT_TO_OBJECT_TYPE:
            obj = child
            object_type = XML_ROOT_TO_OBJECT_TYPE[ln]
            break
    if obj is None:
        object_type, name = _object_type_from_path(path, SourceFormat.XML_EXPORT)
        return MetadataObject(
            object_type=object_type,
            name=name,
            path=str(path),
            source_name=source_name,
            source_format=SourceFormat.XML_EXPORT,
        )

    props = None
    for child in obj:
        if _local_name(child.tag) == "Properties":
            props = child
            break

    name = path.stem
    synonym = ""
    comment = ""
    version = ""
    posting = ""
    real_time_posting = ""
    if props is not None:
        for part in props:
            ln = _local_name(part.tag)
            if ln == "Name":
                name = _text(part) or name
            elif ln == "Synonym":
                synonym = _synonym_xml_export(part)
            elif ln == "Comment":
                comment = _text(part)
            elif ln == "Version":
                version = _text(part)
        posting, real_time_posting = _document_posting_xml_export(props)

    return MetadataObject(
        object_type=object_type,
        name=name,
        synonym=synonym,
        path=str(path),
        source_name=source_name,
        source_format=SourceFormat.XML_EXPORT,
        attributes=_attributes_xml_export(obj),
        tabular_sections=_tabular_sections_xml_export(obj),
        register_records=_register_records_xml_export(obj),
        dimensions=_named_fields_xml_export(obj, "Dimension"),
        resources=_named_fields_xml_export(obj, "Resource"),
        register_type=_register_type_xml_export(obj),
        posting=posting,
        real_time_posting=real_time_posting,
        comment=comment,
        version=version,
        raw_xml_summary=etree.tostring(obj, encoding="unicode")[:2000],
    )


def _form_context_from_path(path: Path) -> tuple[str, str, str]:
    """parent_type, parent_name, form_name (работает с абсолютным путём)."""
    parts = path.parts
    if "CommonForms" in parts:
        idx = parts.index("CommonForms")
        if idx + 1 < len(parts):
            name = parts[idx + 1]
            return "CommonForm", name, name
    if "Forms" in parts:
        idx = parts.index("Forms")
        if idx >= 2 and idx + 1 < len(parts):
            folder = parts[idx - 2]
            parent_type = FOLDER_TO_OBJECT_TYPE.get(folder, folder)
            return parent_type, parts[idx - 1], parts[idx + 1]
    return "Unknown", path.parent.name, path.stem


def _parse_edt_form(path: Path, source_name: str) -> MetadataObject:
    parent_type, parent_name, form_name = _form_context_from_path(path)
    tree = etree.parse(str(path))
    root = tree.getroot()
    synonym = ""
    for child in root:
        if _local_name(child.tag) == "synonym":
            synonym = _synonym_edt(child) or _text(child)
            break
        if _local_name(child.tag) == "Properties":
            for part in child:
                if _local_name(part.tag) == "Synonym":
                    synonym = _synonym_xml_export(part)
    title = _text(root) if _local_name(root.tag) == "name" else form_name
    for child in root:
        if _local_name(child.tag) == "name":
            title = _text(child) or form_name
            break

    return MetadataObject(
        object_type="Form",
        name=title or form_name,
        synonym=synonym,
        path=str(path),
        source_name=source_name,
        source_format=SourceFormat.EDT,
        comment=f"Родитель: {parent_type}.{parent_name}",
        raw_xml_summary=etree.tostring(root, encoding="unicode")[:2000],
    )


def extract_metadata(path: str, source_name: str, fmt: SourceFormat) -> MetadataObject:
    file_path = Path(path)
    if fmt == SourceFormat.EDT:
        if file_path.suffix.lower() == ".form":
            return _parse_edt_form(file_path, source_name)
        return _parse_edt(file_path, source_name)
    return _parse_xml_export(file_path, source_name)
