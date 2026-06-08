"""Тесты рендера markdown-документации."""

from pathlib import Path

from web.docs_render import render_markdown_file
from web.paths import DOCS_DIR


def test_render_plugins_doc_has_html_table():
    path = DOCS_DIR / "01-plugins.md"
    title, html = render_markdown_file(path)
    assert "плагин" in title.lower() or "VS" in title
    assert "<table>" in html
    assert "<h2>" in html
    assert "[01-plugins.md]" not in html


def test_internal_md_links_rewritten():
    source = "# T\n\n[other](02-mcp-docker.md)\n"
    path = Path("/tmp/test-doc.md")
    path.write_text(source, encoding="utf-8")
    try:
        _, html = render_markdown_file(path)
        assert 'href="/docs/02-mcp-docker.md"' in html
    finally:
        path.unlink(missing_ok=True)
