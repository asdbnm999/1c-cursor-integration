from packages.kb.indexer.docker_build import (
    DockerBuildState,
    has_build_history,
    image_exists,
    resolve_pip_build_config,
    tag_profile_image,
)
from packages.kb.indexer.docker_names import SHARED_IMAGE_NAME, container_name, image_name


def test_image_name_matches_container_name():
    assert image_name("bp-30") == container_name("bp-30") == "1c-kb-bp-30-mcp"


def test_has_build_history_false_without_log(monkeypatch, tmp_path):
    import packages.kb.indexer.docker_build as mod

    profile = "demo"
    profile_dir = tmp_path / profile
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "_states", {})
    monkeypatch.setattr(mod, "_active_build_profile", None)
    assert has_build_history(profile) is False


def test_has_build_history_true_with_meta(monkeypatch, tmp_path):
    import packages.kb.indexer.docker_build as mod

    profile = "demo"
    profile_dir = tmp_path / profile
    profile_dir.mkdir(parents=True)
    meta = profile_dir / "build-meta.json"
    meta.write_text('{"status": "completed"}', encoding="utf-8")
    monkeypatch.setattr(mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(mod, "_states", {})
    monkeypatch.setattr(mod, "_active_build_profile", None)
    assert has_build_history(profile) is True


def test_to_dict_includes_profile_image(monkeypatch):
    import packages.kb.indexer.docker_build as mod

    monkeypatch.setattr(mod, "image_exists", lambda _name: False)
    monkeypatch.setattr(mod, "shared_image_exists", lambda: False)
    monkeypatch.setattr(mod, "has_build_history", lambda _name: False)
    data = DockerBuildState(profile_name="testbase").to_dict()
    assert data["image"] == "1c-kb-testbase-mcp"
    assert data["shared_image"] == SHARED_IMAGE_NAME
    assert data["image_exists"] is False
    assert data["shared_image_exists"] is False
    assert data["build_history"] is False


def test_resolve_pip_build_config_from_settings(monkeypatch):
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    monkeypatch.delenv("PIP_TRUSTED_HOST", raising=False)

    import web.settings as settings_mod

    monkeypatch.setattr(
        settings_mod,
        "load_settings",
        lambda: {
            "docker": {
                "pip_index_url": "https://mirror.example/simple/",
                "pip_trusted_host": "mirror.example",
            }
        },
    )
    index, extra, trusted = resolve_pip_build_config()
    assert index == "https://mirror.example/simple/"
    assert extra == "https://mirror.yandex.ru/mirrors/pypi/simple/"
    assert trusted == "mirror.example"


def test_resolve_pip_build_config_env_overrides_settings(monkeypatch):
    monkeypatch.setenv("PIP_INDEX_URL", "https://pypi.org/simple")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://mirror.example/simple/")
    monkeypatch.setenv("PIP_TRUSTED_HOST", "pypi.org")
    index, extra, trusted = resolve_pip_build_config()
    assert index == "https://pypi.org/simple"
    assert extra == "https://mirror.example/simple/"
    assert trusted == "pypi.org"


def test_resolve_pip_build_config_has_builtin_default(monkeypatch):
    monkeypatch.delenv("PIP_INDEX_URL", raising=False)
    monkeypatch.delenv("PIP_EXTRA_INDEX_URL", raising=False)
    monkeypatch.delenv("PIP_TRUSTED_HOST", raising=False)
    import web.settings as settings_mod

    monkeypatch.setattr(settings_mod, "load_settings", lambda: {"docker": {}})
    index, extra, trusted = resolve_pip_build_config()
    assert index == "https://pypi.org/simple"
    assert "mirror.yandex.ru" in extra
    assert "pypi.org" in trusted


def test_shared_image_name_constant():
    assert SHARED_IMAGE_NAME == "1c-kb-mcp:latest"


def test_tag_profile_image_from_shared(monkeypatch):
    import packages.kb.indexer.docker_build as mod

    tagged: list[str] = []

    class FakeImage:
        def tag(self, ref: str) -> None:
            tagged.append(ref)

    class FakeImages:
        @staticmethod
        def get(ref: str):
            if ref == SHARED_IMAGE_NAME:
                return FakeImage()
            raise Exception("not found")

    class FakeClient:
        images = FakeImages

    monkeypatch.setattr(mod, "_docker_image_exists", lambda ref: ref == SHARED_IMAGE_NAME)
    monkeypatch.setattr(mod, "_get_client", lambda: FakeClient())
    result = tag_profile_image("demo")
    assert result == "1c-kb-demo-mcp"
    assert tagged == ["1c-kb-demo-mcp"]


def test_image_exists_uses_profile_image(monkeypatch):
    import packages.kb.indexer.docker_build as mod

    seen = []

    def fake_get(image):
        seen.append(image)
        return object()

    class FakeClient:
        class images:
            @staticmethod
            def get(image):
                return fake_get(image)

    monkeypatch.setattr(mod, "_get_client", lambda: FakeClient())
    assert image_exists("myprof") is True
    assert seen == ["1c-kb-myprof-mcp"]
