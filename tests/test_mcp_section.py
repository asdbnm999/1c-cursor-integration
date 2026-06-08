"""Тесты статуса §2 MCP и конфликтов портов 82xx (ТЗ §6.4, §15)."""

from __future__ import annotations

import socket
from unittest.mock import patch

from web.mcp.constants import SEARXNG_SLUG, SYNTAX_SLUG
from web.mcp.service import (
    auto_mcp_port,
    check_ports_for_server,
    compute_section_status,
    find_port_deploy_conflicts,
    resolve_mcp_port,
)


def _operational_server(slug: str, *, port: int) -> dict:
    url = f"http://127.0.0.1:{port}/mcp"
    return {
        "slug": slug,
        "enabled": True,
        "mcp_url": url,
        "mcp_json_url": url,
        "in_mcp_json": True,
        "container": {"running": True, "health": "healthy"},
    }


def test_compute_section_status_not_started_when_disabled():
    payload = {
        "servers": [
            {"slug": "searxng", "enabled": False, "container": {"running": False}},
            {"slug": "1c-syntax-helper", "enabled": False, "container": {"running": False}},
        ]
    }
    assert compute_section_status(payload) == "not_started"


def test_compute_section_status_ready_both_operational():
    payload = {
        "servers": [
            _operational_server("searxng", port=8201),
            _operational_server("1c-syntax-helper", port=8203),
        ]
    }
    assert compute_section_status(payload) == "ready"


def test_compute_section_status_in_progress_only_searxng():
    payload = {
        "servers": [
            _operational_server("searxng", port=8201),
            {
                "slug": "1c-syntax-helper",
                "enabled": False,
                "ready": False,
                "container": {"running": False, "health": "missing"},
            },
        ]
    }
    assert compute_section_status(payload) == "in_progress"


def test_compute_section_status_in_progress_partial():
    payload = {
        "servers": [
            _operational_server("searxng", port=8201),
            {
                "slug": "1c-syntax-helper",
                "enabled": True,
                "mcp_url": "http://127.0.0.1:8203/mcp",
                "mcp_json_url": "http://127.0.0.1:8203/mcp",
                "in_mcp_json": True,
                "container": {"running": False, "health": "missing"},
            },
        ]
    }
    assert compute_section_status(payload) == "in_progress"


def test_auto_mcp_port_from_container():
    cfg = {"slug": "searxng", "host_port_mcp": 59065}
    with patch("web.mcp.service.container_status", return_value={"running": True}):
        with patch("web.mcp.service.published_host_port", return_value=54035):
            assert auto_mcp_port(SEARXNG_SLUG, cfg) == 54035


def test_resolve_mcp_port_auto_ignores_stale_settings():
    cfg = {"slug": "searxng", "host_port_mcp": 59065, "host_port_mcp_manual": False}
    with patch("web.mcp.service.container_status", return_value={"running": True}):
        with patch("web.mcp.service.published_host_port", return_value=54035):
            port, manual, published, mismatch = resolve_mcp_port(SEARXNG_SLUG, cfg)
    assert port == 54035
    assert manual is False
    assert published == 54035
    assert mismatch is False


def test_resolve_mcp_port_manual_keeps_user_value_when_matches():
    cfg = {"slug": "searxng", "host_port_mcp": 54035, "host_port_mcp_manual": True}
    with patch("web.mcp.service.container_status", return_value={"running": True}):
        with patch("web.mcp.service.published_host_port", return_value=54035):
            port, manual, _, mismatch = resolve_mcp_port(SEARXNG_SLUG, cfg)
    assert port == 54035
    assert manual is True
    assert mismatch is False


def test_resolve_mcp_port_manual_mismatch_before_deploy():
    cfg = {"slug": "searxng", "host_port_mcp": 8201, "host_port_mcp_manual": True}
    with patch("web.mcp.service.container_status", return_value={"running": True}):
        with patch("web.mcp.service.published_host_port", return_value=54035):
            port, manual, _, mismatch = resolve_mcp_port(SEARXNG_SLUG, cfg)
    assert port == 8201
    assert manual is True
    assert mismatch is True


def test_check_ports_searxng_defaults():
    cfg = {"host_port_mcp": 8201, "host_port_core": 8202}
    with patch("web.mcp.service.container_status", return_value={"running": False}):
        ports = check_ports_for_server(SEARXNG_SLUG, cfg)
    assert len(ports) == 2
    assert {p["port"] for p in ports} == {8201, 8202}
    assert all("free" in p for p in ports)


def test_check_ports_syntax_default():
    cfg = {"host_port_mcp": 8203}
    with patch("web.mcp.service.container_status", return_value={"running": False}):
        ports = check_ports_for_server(SYNTAX_SLUG, cfg)
    assert len(ports) == 1
    assert ports[0]["port"] == 8203


def test_check_ports_detects_bound_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        cfg = {
            "host_port_mcp": port,
            "host_port_mcp_manual": True,
            "host_port_core": port + 1,
        }
        with patch("web.mcp.service.container_status", return_value={"running": False}):
            with patch("web.mcp.service.is_port_free", side_effect=lambda p, host="127.0.0.1": p != port):
                ports = check_ports_for_server(SEARXNG_SLUG, cfg)
        busy = [p for p in ports if not p["free"]]
        assert len(busy) == 1
        assert busy[0]["port"] == port


def test_find_port_deploy_conflicts_ignores_own_container():
    cfg = {"slug": "searxng", "host_port_mcp": 8201, "host_port_core": 8202}
    with patch("web.mcp.service.container_status", return_value={"running": True}):
        with patch("web.mcp.service.resolve_mcp_port", return_value=(8201, False, 8201, False)):
            with patch("web.mcp.service.is_port_free", return_value=False):
                conflicts = find_port_deploy_conflicts(SEARXNG_SLUG, cfg)
    assert conflicts == []


def test_find_port_deploy_conflicts_blocks_foreign_process():
    cfg = {"slug": "searxng", "host_port_mcp": 8201, "host_port_core": 8202}
    with patch("web.mcp.service.container_status", return_value={"running": False}):
        with patch(
            "web.mcp.service.check_ports_for_server",
            return_value=[
                {"port": 8201, "role": "MCP", "free": False},
                {"port": 8202, "role": "Core", "free": True},
            ],
        ):
            conflicts = find_port_deploy_conflicts(SEARXNG_SLUG, cfg)
    assert any(item["port"] == 8201 for item in conflicts)


def test_mcp_settings_update_reports_port_conflicts(tmp_path, monkeypatch):
    from web.app import create_app

    app = create_app()
    client = app.test_client()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        busy_port = sock.getsockname()[1]

        def fake_check(slug, cfg):
            return [{"port": busy_port, "role": "MCP", "free": False}]

        monkeypatch.setattr("web.mcp.service.check_ports_for_server", fake_check)
        res = client.put(
            "/mcp/api/settings",
            json={"server": "searxng", "host_port_mcp": busy_port},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data.get("ok") is True
        assert len(data.get("port_conflicts", [])) >= 1
