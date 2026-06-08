from __future__ import annotations

import re
from pathlib import Path

from packages.kb.indexer.models import BslProcedure

PROCEDURE_START_RE = re.compile(
    r"^(Процедура|Функция)\s+([\wА-Яа-яЁё]+)\s*\((.*?)\)\s*(Экспорт)?\s*$",
    re.MULTILINE | re.IGNORECASE,
)
REGION_RE = re.compile(r"^#Область\s+(.+)$", re.MULTILINE)
END_REGION_RE = re.compile(r"^#КонецОбласти", re.MULTILINE)
END_PROC_RE = re.compile(r"^Конец(Процедуры|Функции)\s*$", re.MULTILINE | re.IGNORECASE)


def _find_regions(content: str) -> list[tuple[int, str]]:
    regions: list[tuple[int, str]] = []
    for match in REGION_RE.finditer(content):
        line_no = content[: match.start()].count("\n") + 1
        regions.append((line_no, match.group(1).strip()))
    return regions


def _region_at_line(regions: list[tuple[int, str]], line_no: int) -> str:
    current = ""
    for start_line, name in regions:
        if start_line <= line_no:
            current = name
        else:
            break
    return current


def extract_bsl_procedures(path: str) -> list[BslProcedure]:
    content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    regions = _find_regions(content)
    procedures: list[BslProcedure] = []

    starts = list(PROCEDURE_START_RE.finditer(content))
    for idx, match in enumerate(starts):
        kind = match.group(1)
        name = match.group(2)
        params = match.group(3).strip()
        is_export = bool(match.group(4))
        start_line = content[: match.start()].count("\n") + 1
        start_pos = match.start()

        if idx + 1 < len(starts):
            end_pos = starts[idx + 1].start()
        else:
            end_pos = len(content)

        body = content[start_pos:end_pos]
        end_match = None
        for end_candidate in END_PROC_RE.finditer(body):
            end_match = end_candidate
        if end_match:
            body = body[: end_match.end()]

        end_line = start_line + body.count("\n")
        signature = f"{kind} {name}({params})" + (" Экспорт" if is_export else "")

        procedures.append(
            BslProcedure(
                name=name,
                kind=kind,
                is_export=is_export,
                region=_region_at_line(regions, start_line),
                body=body.strip(),
                start_line=start_line,
                end_line=end_line,
                signature=signature,
            )
        )

    return procedures


def extract_module_header(path: str, max_lines: int = 80) -> str:
    content = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    lines = content.splitlines()
    header_lines: list[str] = []
    for line in lines[:max_lines]:
        stripped = line.strip()
        if PROCEDURE_START_RE.match(stripped):
            break
        header_lines.append(line)
    return "\n".join(header_lines).strip()
