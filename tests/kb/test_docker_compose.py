from pathlib import Path

from packages.kb.indexer.config import ProfileConfig, DockerConfig, IndexingConfig, ChunkingConfig, EmbeddingsConfig, StoreConfig, McpConfig, DocsConfig
from packages.kb.indexer.docker_compose import compose_file_path, compose_project_name, render_compose_yaml, write_compose_file
from packages.kb.indexer.docker_names import container_name, image_name
from packages.kb.indexer.profiles import PROJECT_ROOT


def _sample_config(profile_name: str = "testbase", port: int = 8301) -> ProfileConfig:
    return ProfileConfig(
        profile_name=profile_name,
        display_name="Test",
        format="edt",
        root=Path("/tmp/project"),
        src="src",
        indexing=IndexingConfig(),
        docs=DocsConfig(),
        chunking=ChunkingConfig(),
        embeddings=EmbeddingsConfig(),
        store=StoreConfig(path=f"data/profiles/{profile_name}/chroma", collection=profile_name),
        mcp=McpConfig(server_name=f"1c-kb-{profile_name}", port=port),
        docker=DockerConfig(compose_dir=""),
        config_path=PROJECT_ROOT / "profiles" / profile_name / "config.yaml",
    )


def test_render_compose_yaml_contains_profile_and_port():
    config = _sample_config("myprofile", 8305)
    text = render_compose_yaml(config)
    assert "name: 1c-kb-myprofile-mcp" in text
    assert "image: 1c-kb-myprofile-mcp" in text
    assert "container_name: 1c-kb-myprofile-mcp" in text
    assert '"8305:8000"' in text or "8305:8000" in text
    assert "KB_PROFILE: myprofile" in text
    assert str(PROJECT_ROOT.resolve()) in text
    assert "healthcheck:" in text
    assert "profiles:/app/profiles:ro" in text.replace(" ", "")
    assert "mem_limit:" in text
    assert "build:" not in text


def test_render_compose_yaml_gpu_block():
    config = _sample_config("gpu-demo", 8310)
    config.docker.gpu = True
    text = render_compose_yaml(config)
    assert "nvidia" in text
    assert "capabilities: [gpu]" in text


def test_write_compose_file_creates_yaml(tmp_path: Path):
    config = _sample_config("demo", 8302)
    path = write_compose_file(tmp_path / "1c-kb-demo", config)
    assert path == compose_file_path(tmp_path / "1c-kb-demo")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert compose_project_name("demo") in content
    assert container_name("demo") in content
    assert f"image: {image_name('demo')}" in content
