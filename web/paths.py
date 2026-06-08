"""Корневые пути monorepo 1c-cursor."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
ASSETS_DIR = PROJECT_ROOT / "assets"
EXTENSIONS_DIR = ASSETS_DIR / "extensions"
PROFILES_DIR = PROJECT_ROOT / "profiles"
DOCKER_TEMPLATES_DIR = PROJECT_ROOT / "docker_templates"
DOCS_DIR = PROJECT_ROOT / "docs"

SETTINGS_PATH = DATA_DIR / "settings.json"
SETTINGS_EXAMPLE_PATH = DATA_DIR / "settings.json.example"
CURSOR_SETTINGS_PATH = DATA_DIR / "cursor-settings.json"
CURSOR_SETTINGS_EXAMPLE_PATH = DATA_DIR / "cursor-settings.json.example"
MCP_BACKUPS_DIR = DATA_DIR / "cursor-mcp-backups"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080

DEFAULT_DOCKER_ROOT = Path.home() / "DockerMCP"
