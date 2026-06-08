"""Мастер onboarding: определение формата, preview, оценка времени."""

from __future__ import annotations

from pathlib import Path

from packages.kb.indexer.constants import BSL_MODULE_NAMES
from packages.kb.indexer.exceptions import WizardError
from packages.kb.indexer.profile_ops import get_default_indexing


def detect_format(root: Path) -> str | None:
    """Определяет edt или xml_export по структуре каталога."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        return None

    src = root / "src"
    if src.is_dir() and any(src.rglob("*.mdo")):
        return "edt"

    if (root / "Configuration.xml").is_file():
        return "xml_export"

    for folder in ("Documents", "Catalogs", "CommonModules"):
        if (root / folder).is_dir():
            return "xml_export"

    if any(root.rglob("*.mdo")):
        return "edt"

    return None


def scan_preview(root: Path, fmt: str) -> dict:
    """Быстрый подсчёт файлов без полного индекса."""
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise WizardError("Каталог не найден", details=str(root))

    base = root / "src" if fmt == "edt" and (root / "src").is_dir() else root
    if not base.exists():
        raise WizardError("Базовый каталог недоступен", details=str(base))

    metadata = 0
    bsl = 0
    forms = 0

    if fmt == "edt":
        for mdo in base.rglob("*.mdo"):
            rel = mdo.relative_to(base)
            if "Forms" not in rel.parts:
                metadata += 1
        for form_file in base.rglob("*.form"):
            rel = form_file.relative_to(base)
            if rel.name == "Form.form" and (
                "Forms" in rel.parts or rel.parts[0] == "CommonForms"
            ):
                forms += 1
        for f in base.rglob("*.bsl"):
            if f.name in BSL_MODULE_NAMES:
                bsl += 1
                rel = f.relative_to(base)
                if "Forms" in rel.parts or (
                    rel.parts[0] == "CommonForms" and f.name in BSL_MODULE_NAMES
                ):
                    forms += 1
    else:
        for xml in base.rglob("*.xml"):
            rel = xml.relative_to(base)
            if len(rel.parts) == 1 and rel.name == "Configuration.xml":
                metadata += 1
            elif len(rel.parts) == 2 and rel.suffix == ".xml":
                metadata += 1
            elif "Forms" in rel.parts:
                forms += 1
        for f in base.rglob("*.bsl"):
            if f.name in BSL_MODULE_NAMES:
                bsl += 1

    md = sum(1 for _ in root.rglob("*.md"))
    total = metadata + bsl + md

    return {
        "root": str(root),
        "format": fmt,
        "source_base": str(base),
        "metadata_files": metadata,
        "bsl_files": bsl,
        "form_modules": forms,
        "markdown_files": md,
        "total_indexable": total,
        "default_indexing": get_default_indexing(fmt),
    }


def estimate_index_time(preview: dict, *, include_forms: bool = False) -> dict:
    """Грубая оценка времени индексации."""
    meta = preview.get("metadata_files", 0)
    bsl = preview.get("bsl_files", 0)
    forms = preview.get("form_modules", 0) if include_forms else 0
    md = preview.get("markdown_files", 0)

    # ~0.05 с на файл метаданных, ~0.15 на BSL, embedding batch amortized
    files = meta + bsl + forms + md
    chunks_est = int(meta * 1.2 + bsl * 8 + forms * 3 + md * 2)
    seconds = max(30, int(files * 0.08 + chunks_est * 0.002))

    hours, rem = divmod(seconds, 3600)
    mins, secs = divmod(rem, 60)

    if hours:
        human = f"~{hours} ч {mins} мин"
    elif mins:
        human = f"~{mins} мин"
    else:
        human = f"~{secs} сек"

    return {
        "files_estimated": files,
        "chunks_estimated": chunks_est,
        "seconds_estimated": seconds,
        "human": human,
        "note": "Оценка для CPU; GPU и OpenAI могут отличаться",
    }


def run_wizard(root: str | Path, *, include_forms: bool = False) -> dict:
    """Полный preview для мастера."""
    root_path = Path(root).expanduser().resolve()
    fmt = detect_format(root_path)
    if fmt is None:
        raise WizardError(
            "Не удалось определить формат",
            details="Ожидается EDT (src/*.mdo) или XML-выгрузка (Configuration.xml)",
        )
    preview = scan_preview(root_path, fmt)
    estimate = estimate_index_time(preview, include_forms=include_forms)
    return {
        "detected_format": fmt,
        "preview": preview,
        "estimate": estimate,
        "suggested_src": "src" if fmt == "edt" else "",
        "include_forms_recommended": preview.get("form_modules", 0) > 0,
    }
