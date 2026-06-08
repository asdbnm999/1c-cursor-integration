"""Рендер markdown-документации §22 в читаемый HTML."""

from __future__ import annotations

import re
from pathlib import Path

import markdown
from markdown.extensions.fenced_code import FencedCodeExtension
from markdown.extensions.tables import TableExtension

_MD = markdown.Markdown(
    extensions=[
        TableExtension(),
        FencedCodeExtension(),
        "nl2br",
        "sane_lists",
    ]
)


def _rewrite_internal_links(html: str) -> str:
    """Относительные .md → /docs/… для навигации внутри приложения."""

    def repl(match: re.Match[str]) -> str:
        href = match.group(1)
        if href.startswith(("/", "http://", "https://", "mailto:", "#")):
            return match.group(0)
        if ".." in href:
            return match.group(0)
        clean = href.lstrip("./")
        return f'href="/docs/{clean}"'

    return re.sub(r'href="([^"]+\.md)"', repl, html)


def _extract_title(source: str, fallback: str) -> str:
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
    return fallback


def render_markdown_file(path: Path) -> tuple[str, str]:
    """
    Прочитать .md и вернуть (title, html_body).
    html_body — фрагмент для вставки в шаблон (без обёртки <html>).
    """
    source = path.read_text(encoding="utf-8")
    title = _extract_title(source, path.stem)
    _MD.reset()
    body = _MD.convert(source)
    body = _rewrite_internal_links(body)
    return title, body
