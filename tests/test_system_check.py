"""Тесты system_check (шаг 1)."""

from __future__ import annotations

from unittest.mock import patch

from web.system_check import (
    get_port_registry,
    get_python_info,
    is_port_free,
    run_system_diagnostics,
)


def test_python_info_ok():
    info = get_python_info()
    assert info["ok"] is True
    assert "version" in info


def test_is_port_free_detects_bound_port():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        assert is_port_free(port) is False


def test_is_port_free_detects_listening_service():
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        assert is_port_free(port) is False


def test_port_registry_includes_standard_ports():
    ports = {p["port"] for p in get_port_registry()}
    assert 8201 in ports
    assert 8202 in ports
    assert 8203 in ports


def test_run_system_diagnostics_structure():
    with patch("web.system_check.get_docker_status", return_value={"running": True, "message": "ok"}):
        data = run_system_diagnostics()
    assert "python" in data
    assert "docker" in data
    assert "ports" in data
    assert "warnings" in data


def test_port_registry_kb_profile_port(monkeypatch):
    monkeypatch.setattr(
        "web.system_check.load_settings",
        lambda: {
            "mcp": {
                "kb_profiles": {"demo": {"host_port": 8303}},
                "standard": {},
            }
        },
    )
    ports = {p["port"]: p["role"] for p in get_port_registry()}
    assert 8303 in ports
    assert "demo" in ports[8303]


def test_collect_warnings_busy_ports(monkeypatch):
    from web.system_check import _collect_warnings

    monkeypatch.setattr(
        "web.system_check.get_port_registry",
        lambda: [{"port": 8201, "free": False, "role": "SearXNG MCP", "status": "in_use"}],
    )
    warnings = _collect_warnings({"running": True})
    assert any("8201" in w for w in warnings)


def test_kb_port_base_constant():
    from web.system_check import KB_PORT_BASE

    assert KB_PORT_BASE == 8301


def test_estimate_mcp_ram_structure():
    from web.system_check import estimate_mcp_ram_mb

    data = estimate_mcp_ram_mb()
    assert "total_mb" in data
    assert "breakdown" in data
    assert isinstance(data["breakdown"], list)
    stacks = [item["stack"] for item in data["breakdown"]]
    assert "SearXNG" in stacks
    assert "1C Syntax Helper" in stacks
