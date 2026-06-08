from pathlib import Path

import yaml

from packages.kb.indexer.docker_compose import default_compose_dir
from packages.kb.indexer.profile_ops import ensure_default_compose_dir


def test_ensure_default_compose_dir_writes_config(tmp_path, monkeypatch):
    profile = "test-base"
    profiles_root = tmp_path / "profiles"
    profiles_root.mkdir()
    profile_dir = profiles_root / profile
    profile_dir.mkdir()
    config_path = profile_dir / "config.yaml"
    config_path.write_text(
        yaml.dump(
            {
                "profile": {"name": profile},
                "docker": {"compose_dir": ""},
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    import packages.kb.indexer.profile_ops as ops

    monkeypatch.setattr(ops, "profile_config_path", lambda name: profiles_root / name / "config.yaml")
    monkeypatch.setattr(ops, "profile_dir", lambda name: profiles_root / name)
    monkeypatch.setattr(
        "packages.kb.indexer.docker_compose.default_compose_dir",
        lambda name: tmp_path / "DockerMCP" / f"1c-kb-{name}",
    )

    result = ensure_default_compose_dir(profile)
    expected = str(tmp_path / "DockerMCP" / f"1c-kb-{profile}")
    assert result == expected
    assert (tmp_path / "DockerMCP" / f"1c-kb-{profile}").is_dir()

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert raw["docker"]["compose_dir"] == expected


def test_ensure_default_compose_dir_keeps_existing(tmp_path, monkeypatch):
    profile = "demo"
    profiles_root = tmp_path / "profiles"
    profile_dir = profiles_root / profile
    profile_dir.mkdir(parents=True)
    existing = str(tmp_path / "custom-compose")
    config_path = profile_dir / "config.yaml"
    config_path.write_text(
        yaml.dump({"docker": {"compose_dir": existing}}, allow_unicode=True),
        encoding="utf-8",
    )

    import packages.kb.indexer.profile_ops as ops

    monkeypatch.setattr(ops, "profile_config_path", lambda name: profiles_root / name / "config.yaml")

    assert ensure_default_compose_dir(profile) == existing


def test_default_compose_dir_under_dockermcp():
    path = default_compose_dir("myprof")
    assert path == Path.home() / "DockerMCP" / "1c-kb-myprof"
