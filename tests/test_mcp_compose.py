"""Тесты генерации compose §2 (ТЗ §10, §7)."""

from __future__ import annotations

from pathlib import Path

import yaml

from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG
from web.mcp_compose import compose_needs_regenerate, generate_compose, mcp_url
from web.mcp.syntax_patch import PATCH_MARKER, apply_mcp_patch, is_patched
from web.system_check import is_port_free


def test_mcp_url_uses_127():
    assert mcp_url(8201) == "http://127.0.0.1:8201/mcp"


def test_generate_searxng_compose_naming(tmp_path: Path):
    cfg = {
        "slug": "searxng",
        "host_port_mcp": 8201,
        "host_port_core": 8202,
        "secret_key": "test-secret",
        "resource_preset": "economical",
        "use_external_volumes": True,
    }
    result = generate_compose(SEARXNG_SLUG, cfg, target_dir=tmp_path / "searxng")
    compose = yaml.safe_load((tmp_path / "searxng" / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["name"] == "searxng-mcp"
    assert "searxng-mcp" in compose["services"]
    assert "searxng-mcp-valkey" in compose["services"]
    assert "searxng-mcp-core" in compose["services"]
    assert compose["services"]["searxng-mcp"]["container_name"] == "searxng-mcp"
    assert "8201:8201" in compose["services"]["searxng-mcp"]["ports"][0]
    assert "8202:" in compose["services"]["searxng-mcp-core"]["ports"][0]

    settings = yaml.safe_load((tmp_path / "searxng" / "core-config" / "settings.yml").read_text())
    assert "json" in settings["search"]["formats"]
    assert settings["server"]["secret_key"] == "test-secret"

    hc = compose["services"]["searxng-mcp"]["healthcheck"]["test"][1]
    assert "127.0.0.1:8201" in hc

    assert result["mcp_url"] == mcp_url(8201)


def test_generate_syntax_compose_naming(tmp_path: Path):
    cfg = {
        "slug": "1c-syntax-helper",
        "host_port_mcp": 8203,
        "hbk_path": "/tmp/hbk/shcntx_ru.hbk",
        "resource_preset": "economical",
        "use_external_volumes": True,
    }
    result = generate_compose(SYNTAX_SLUG, cfg, target_dir=tmp_path / "syntax")
    compose = yaml.safe_load((tmp_path / "syntax" / "docker-compose.yml").read_text(encoding="utf-8"))

    assert compose["name"] == "1c-syntax-helper-mcp"
    assert "1c-syntax-helper-mcp" in compose["services"]
    assert "1c-syntax-helper-mcp-es" in compose["services"]
    assert "8203:8000" in compose["services"]["1c-syntax-helper-mcp"]["ports"][0]
    assert compose["services"]["1c-syntax-helper-mcp"]["environment"]["ELASTICSEARCH_HOST"] == "1c-syntax-helper-mcp-es"

    vol = compose["services"]["1c-syntax-helper-mcp"]["volumes"][0]
    assert vol.endswith("/hbk:/app/data/hbk:ro")
    assert "shcntx" not in vol
    assert result["mcp_url"] == mcp_url(8203)


def test_syntax_patch_idempotent(tmp_path: Path):
    repo = tmp_path / "1c-syntax-helper-mcp"
    mcp_py = repo / "src" / "api" / "routes" / "mcp.py"
    mcp_py.parent.mkdir(parents=True)
    mcp_py.write_text(
        'async def handler():\n    if True:\n        pass\n    elif method == "tools/call":\n        pass\n',
        encoding="utf-8",
    )
    first = apply_mcp_patch(repo)
    assert first["status"] == "patched"
    assert is_patched(mcp_py)
    second = apply_mcp_patch(repo)
    assert second["status"] == "skipped"
    assert PATCH_MARKER in mcp_py.read_text(encoding="utf-8")


def test_compose_needs_regenerate_detects_legacy_syntax(tmp_path: Path):
    legacy = tmp_path / "docker-compose.yml"
    legacy.write_text(
        """
name: 1c-syntax-mcp
services:
  mcp-1c:
    ports:
      - "8000:8000"
""".strip(),
        encoding="utf-8",
    )
    cfg = {
        "slug": "1c-syntax-helper",
        "host_port_mcp": 8203,
        "hbk_path": "/tmp/hbk/shcntx_ru.hbk",
    }
    assert compose_needs_regenerate(SYNTAX_SLUG, cfg, legacy) is True

    generate_compose(SYNTAX_SLUG, cfg, target_dir=tmp_path)
    assert compose_needs_regenerate(SYNTAX_SLUG, cfg, legacy) is False


def test_port_registry_defaults_free_or_busy():
    """Порты 82xx проверяются без падения."""
    for port in (8201, 8202, 8203):
        assert isinstance(is_port_free(port), bool)
