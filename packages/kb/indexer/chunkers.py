from __future__ import annotations

import hashlib
from pathlib import Path

from packages.kb.indexer.config import ProfileConfig
from packages.kb.indexer.models import (
    BslProcedure,
    Chunk,
    DocSection,
    MetadataObject,
    SubsystemInfo,
)


def content_hash(kind: str, path: str, anchor: str, content: str) -> str:
    payload = f"{kind}|{path}|{anchor}|{content}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def build_prefix(
    *,
    project_name: str,
    object_type: str,
    object_name: str,
    path: str,
    subsystems: list[str] | None = None,
    extra: str = "",
) -> str:
    lines = [f"[{project_name} | {object_type} | {object_name}]"]
    if subsystems:
        lines.append(f"Подсистемы: {', '.join(subsystems)}")
    if extra:
        lines.append(extra)
    lines.append(f"Файл: {path}")
    lines.append("---")
    return "\n".join(lines)


def chunk_metadata(config: ProfileConfig, obj: MetadataObject) -> list[Chunk]:
    header = build_prefix(
        project_name=config.display_name,
        object_type=obj.object_type,
        object_name=obj.name,
        path=obj.path,
        subsystems=obj.subsystems,
        extra=f"Синоним: {obj.synonym}" if obj.synonym else "",
    )

    body_parts: list[str] = []
    if obj.comment:
        body_parts.append(f"Комментарий: {obj.comment}")
    if obj.version:
        body_parts.append(f"Версия: {obj.version}")
    if obj.attributes:
        body_parts.append("Реквизиты:")
        body_parts.extend(
            f"- {a['name']}: {a.get('type', '?')}"
            + (f" ({a['synonym']})" if a.get("synonym") else "")
            for a in obj.attributes
        )
    if obj.tabular_sections:
        body_parts.append("\nТабличные части:")
        for ts in obj.tabular_sections:
            attrs = ", ".join(f"{a['name']}: {a.get('type', '?')}" for a in ts.get("attributes", []))
            body_parts.append(f"- {ts['name']}: {attrs}")
    if obj.register_records:
        body_parts.append("\nДвижения по регистрам:")
        body_parts.extend(f"- {r}" for r in obj.register_records)

    text = header + "\n" + "\n".join(body_parts)
    return [
        Chunk(
            id=content_hash("metadata", obj.path, obj.name, text),
            text=text,
            metadata={
                "kind": "metadata",
                "object_type": obj.object_type,
                "object_name": obj.name,
                "path": obj.path,
                "profile": config.profile_name,
                "source_format": obj.source_format.value,
                "subsystems": ",".join(obj.subsystems),
                "register_records": ",".join(obj.register_records),
                "attributes_count": len(obj.attributes),
            },
        )
    ]


def _infer_module_name(path: str) -> str:
    parts = Path(path).parts
    type_folders = {
        "CommonModules", "Documents", "Catalogs", "DataProcessors",
        "Reports", "InformationRegisters", "AccumulationRegisters",
    }
    for idx, part in enumerate(parts):
        if part in type_folders and idx + 1 < len(parts):
            return parts[idx + 1]
    return Path(path).stem


def chunk_bsl(
    config: ProfileConfig,
    module_path: str,
    procedures: list[BslProcedure],
    module_header: str = "",
    object_type: str = "BSLModule",
) -> list[Chunk]:
    chunks: list[Chunk] = []
    module_name = _infer_module_name(module_path)

    if module_header.strip():
        header_text = build_prefix(
            project_name=config.display_name,
            object_type=object_type,
            object_name=module_name,
            path=module_path,
            extra="Тип чанка: заголовок модуля",
        )
        text = header_text + "\n" + module_header
        chunks.append(
            Chunk(
                id=content_hash("bsl_module_header", module_path, "header", text),
                text=text,
                metadata={
                    "kind": "bsl_module_header",
                    "object_type": object_type,
                    "object_name": module_name,
                    "module": module_name,
                    "path": module_path,
                    "profile": config.profile_name,
                },
            )
        )

    for proc in procedures:
        extra = f"Процедура: {proc.signature}"
        if proc.region:
            extra += f"\nОбласть: {proc.region}"
        if proc.is_export:
            extra += "\nЭкспорт: да"

        header_text = build_prefix(
            project_name=config.display_name,
            object_type=object_type,
            object_name=module_name,
            path=module_path,
            extra=extra,
        )
        text = header_text + "\n" + proc.body
        chunks.append(
            Chunk(
                id=content_hash("bsl_procedure", module_path, proc.name, text),
                text=text,
                metadata={
                    "kind": "bsl_procedure",
                    "object_type": object_type,
                    "object_name": module_name,
                    "module": module_name,
                    "procedure": proc.name,
                    "is_export": proc.is_export,
                    "region": proc.region,
                    "path": module_path,
                    "profile": config.profile_name,
                    "start_line": proc.start_line,
                    "end_line": proc.end_line,
                },
            )
        )
    return chunks


def chunk_subsystem(config: ProfileConfig, subsystem: SubsystemInfo) -> list[Chunk]:
    header = build_prefix(
        project_name=config.display_name,
        object_type="Subsystem",
        object_name=subsystem.name,
        path=subsystem.path,
        extra=f"Синоним: {subsystem.synonym}" if subsystem.synonym else "",
    )
    body_parts: list[str] = []
    if subsystem.parent:
        body_parts.append(f"Родитель: {subsystem.parent}")
    if subsystem.children:
        body_parts.append("Дочерние подсистемы: " + ", ".join(subsystem.children))
    if subsystem.content:
        body_parts.append("Объекты:")
        body_parts.extend(f"- {item}" for item in subsystem.content)

    text = header + "\n" + "\n".join(body_parts)
    return [
        Chunk(
            id=content_hash("subsystem", subsystem.path, subsystem.name, text),
            text=text,
            metadata={
                "kind": "subsystem",
                "object_type": "Subsystem",
                "object_name": subsystem.name,
                "path": subsystem.path,
                "profile": config.profile_name,
                "parent": subsystem.parent,
            },
        )
    ]


def chunk_doc(config: ProfileConfig, section: DocSection) -> Chunk:
    header = build_prefix(
        project_name=config.display_name,
        object_type="Doc",
        object_name=section.title,
        path=section.path,
        extra=f"Раздел: {section.section}",
    )
    text = header + "\n" + section.body
    return Chunk(
        id=content_hash("doc", section.path, section.title, text),
        text=text,
        metadata={
            "kind": "doc",
            "object_type": "Doc",
            "object_name": section.title,
            "path": section.path,
            "profile": config.profile_name,
            "section": section.section,
        },
    )
