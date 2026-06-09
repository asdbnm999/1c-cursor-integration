import json

from packages.kb.indexer.docker_build import BuildStatus, get_build_state


def test_stale_building_marked_interrupted_on_reload(monkeypatch, tmp_path):
    import packages.kb.indexer.docker_build as mod

    profile = "test-base"
    profile_dir = tmp_path / profile
    profile_dir.mkdir(parents=True)
    (profile_dir / "build-meta.json").write_text(
        json.dumps(
            {
                "status": "building",
                "message": "Сборка образа…",
                "error": "",
                "image": "1c-kb-test-base-mcp",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (profile_dir / "build.log").write_text(
        "=== Сборка образа ===\n#12 install-kb-deps.sh\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "_states", {})
    monkeypatch.setattr(mod, "_active_build_profile", None)
    monkeypatch.setattr(mod, "_orphan_watchers", set())
    monkeypatch.setattr(mod, "image_exists", lambda _name: False)
    monkeypatch.setattr(mod, "_is_external_docker_build_running", lambda _image: False)

    state = get_build_state(profile)
    assert state.status == BuildStatus.INTERRUPTED
    assert "перезапуск" in state.message.lower()
    assert any("перезапущен" in line for line in state.log_lines)


def test_stale_building_kept_when_docker_still_runs(monkeypatch, tmp_path):
    import packages.kb.indexer.docker_build as mod

    profile = "demo"
    profile_dir = tmp_path / profile
    profile_dir.mkdir(parents=True)
    (profile_dir / "build-meta.json").write_text(
        json.dumps({"status": "building", "message": "old", "image": "1c-kb-demo-mcp"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "_states", {})
    monkeypatch.setattr(mod, "_active_build_profile", None)
    monkeypatch.setattr(mod, "_orphan_watchers", set())
    monkeypatch.setattr(mod, "_is_external_docker_build_running", lambda _image: True)
    monkeypatch.setattr(mod, "_start_orphan_build_watcher", lambda _profile: None)

    state = get_build_state(profile)
    assert state.status == BuildStatus.BUILDING
    assert "фоне" in state.message
