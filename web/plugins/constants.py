"""Константы раздела VS-плагинов."""

from __future__ import annotations

# Bundled VSIX (ТЗ §9.2) — оба обязательны для статуса «Готово».
BUNDLED_VSIX_FILENAMES: tuple[str, ...] = (
    "1c-configuration-tree-2.10.7.vsix",
    "1c-syntax.language-1c-bsl-1.33.2.vsix",
)

VSIX_GLOB = "*.vsix"
