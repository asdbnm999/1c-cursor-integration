from pathlib import Path

from packages.kb.indexer import docker_wheels as mod


def test_pip_wheel_target_uses_x86_manylinux_on_arm64_mac(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "arm64")
    plat, py_ver, abi = mod._pip_wheel_target()
    assert plat == "manylinux_2_28_x86_64"
    assert py_ver == "3.12"
    assert abi == "cp312"
    assert mod.resolve_docker_build_platform() == "linux/amd64"


def test_pip_wheel_target_x86_host(monkeypatch):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    plat, _py_ver, _abi = mod._pip_wheel_target()
    assert plat == "manylinux_2_28_x86_64"


def test_wheels_cache_ready_checks_marker(tmp_path, monkeypatch):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    req = tmp_path / "req.txt"
    req.write_text("mcp>=1.0.0\n", encoding="utf-8")
    for idx in range(35):
        (wheels / f"pkg-{idx}-1.0.0-py3-none-any.whl").write_bytes(b"x")
    for pkg in mod._REQUIRED_PACKAGES:
        (wheels / f"{pkg}-1.0.0-cp312-cp312-manylinux_2_28_x86_64.whl").write_bytes(b"x")

    monkeypatch.setattr(mod, "WHEELS_DIR", wheels)
    monkeypatch.setattr(mod, "REQUIREMENTS_FILE", req)
    monkeypatch.setattr(mod, "MARKER_FILE", wheels / ".wheels-complete")
    monkeypatch.setattr(mod, "_requirements_fingerprint", lambda: "abc123")

    mod.MARKER_FILE.write_text("abc123\n", encoding="utf-8")
    assert mod.wheels_cache_ready() is True

    mod.MARKER_FILE.write_text("stale\n", encoding="utf-8")
    assert mod.wheels_cache_ready() is False


def test_resolve_pip_legacy_yandex_only_uses_pypi_default(monkeypatch):
    from packages.kb.indexer.docker_build import resolve_pip_build_config

    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    monkeypatch.delenv("PIP_EXTRA_INDEX_URL", raising=False)
    import web.settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "load_settings",
        lambda: {
            "docker": {
                "pip_index_url": "https://mirror.yandex.ru/mirrors/pypi/simple/",
                "pip_trusted_host": "mirror.yandex.ru",
            }
        },
    )
    index, extra, _trusted = resolve_pip_build_config()
    assert index == "https://pypi.org/simple"
    assert "mirror.yandex.ru" in extra
