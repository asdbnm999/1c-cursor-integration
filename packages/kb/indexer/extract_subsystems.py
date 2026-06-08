from __future__ import annotations

from pathlib import Path

from lxml import etree

from packages.kb.indexer.extract_metadata import _local_name, _synonym_edt, _text
from packages.kb.indexer.models import SourceFormat, SubsystemInfo


def _content_items_edt(root: etree._Element) -> list[str]:
    items: list[str] = []
    for child in root:
        if _local_name(child.tag) == "content":
            value = _text(child)
            if value:
                items.append(value)
    return items


def extract_subsystem(path: str, source_name: str, fmt: SourceFormat) -> SubsystemInfo | None:
    file_path = Path(path)
    if fmt != SourceFormat.EDT:
        return None
    if "Subsystems" not in file_path.parts:
        return None

    tree = etree.parse(str(path))
    root = tree.getroot()
    name = file_path.stem
    synonym = ""
    for child in root:
        if _local_name(child.tag) == "name":
            name = _text(child) or name
        elif _local_name(child.tag) == "synonym":
            synonym = _synonym_edt(root)

    parent = ""
    parts = file_path.parts
    if "Subsystems" in parts:
        idx = parts.index("Subsystems")
        if idx + 2 < len(parts) - 1:
            parent = parts[-2]

    children: list[str] = []
    for child in root:
        if _local_name(child.tag) == "subsystems":
            for sub in child:
                if _local_name(sub.tag) == "name":
                    value = _text(sub)
                    if value:
                        children.append(value)

    return SubsystemInfo(
        name=name,
        synonym=synonym,
        path=str(path),
        source_name=source_name,
        parent=parent,
        children=children,
        content=_content_items_edt(root),
    )
