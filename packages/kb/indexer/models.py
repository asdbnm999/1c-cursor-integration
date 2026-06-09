from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class FileKind(str, Enum):
    METADATA = "metadata"
    BSL = "bsl"
    MARKDOWN = "md"
    OTHER = "other"


class SourceFormat(str, Enum):
    EDT = "edt"
    XML_EXPORT = "xml_export"


class FileEntry(BaseModel):
    path: str
    kind: FileKind
    source_name: str
    source_format: SourceFormat
    relative_path: str


class BslProcedure(BaseModel):
    name: str
    kind: str  # Процедура | Функция
    is_export: bool = False
    region: str = ""
    body: str
    start_line: int
    end_line: int
    signature: str = ""


class MetadataObject(BaseModel):
    object_type: str
    name: str
    synonym: str = ""
    path: str
    source_name: str
    source_format: SourceFormat
    subsystems: list[str] = Field(default_factory=list)
    attributes: list[dict[str, Any]] = Field(default_factory=list)
    tabular_sections: list[dict[str, Any]] = Field(default_factory=list)
    register_records: list[str] = Field(default_factory=list)
    dimensions: list[dict[str, Any]] = Field(default_factory=list)
    resources: list[dict[str, Any]] = Field(default_factory=list)
    register_type: str = ""
    posting: str = ""
    real_time_posting: str = ""
    comment: str = ""
    version: str = ""
    raw_xml_summary: str = ""


class SubsystemInfo(BaseModel):
    name: str
    synonym: str = ""
    path: str
    source_name: str
    parent: str = ""
    children: list[str] = Field(default_factory=list)
    content: list[str] = Field(default_factory=list)


class DocSection(BaseModel):
    title: str
    section: str
    body: str
    path: str
    source_name: str


class Chunk(BaseModel):
    id: str
    text: str
    metadata: dict[str, Any]
    embedding: list[float] | None = None
