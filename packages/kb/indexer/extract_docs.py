from __future__ import annotations

import re
from pathlib import Path

from packages.kb.indexer.models import DocSection

HEADING_RE = re.compile(r"^(#{2,3})\s+(.+)$", re.MULTILINE)


def extract_doc_sections(path: str, source_name: str) -> list[DocSection]:
    content = Path(path).read_text(encoding="utf-8", errors="replace")
    matches = list(HEADING_RE.finditer(content))
    if not matches:
        return [
            DocSection(
                title=Path(path).stem,
                section="",
                body=content.strip(),
                path=path,
                source_name=source_name,
            )
        ]

    sections: list[DocSection] = []
    for idx, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
        body = content[start:end].strip()
        section_label = "H2" if level == 2 else "H3"
        sections.append(
            DocSection(
                title=title,
                section=section_label,
                body=body,
                path=path,
                source_name=source_name,
            )
        )
    return sections
