from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from packages.kb.indexer.constants import (
    DEFAULT_EDT_EXCLUDE_GLOBS,
    DEFAULT_EDT_INCLUDE_DIRS,
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_XML_EXCLUDE_GLOBS,
    DEFAULT_XML_INCLUDE_DIRS,
)
from packages.kb.indexer.profiles import PROJECT_ROOT, resolve_profile_config


@dataclass
class IndexingConfig:
    include_dirs: list[str] = field(default_factory=list)
    exclude_dirs: list[str] = field(default_factory=list)
    exclude_globs: list[str] = field(default_factory=list)
    include_forms: bool = False


@dataclass
class WatchConfig:
    enabled: bool = False
    mode: str = "poll"  # poll | watchdog
    poll_interval_sec: float = 2.0
    debounce_sec: float = 3.0


@dataclass
class SearchConfig:
    hybrid: bool = True
    vector_weight: float = 0.65
    keyword_weight: float = 0.35


@dataclass
class ChunkingConfig:
    target_tokens: int = 800
    overlap_ratio: float = 0.12
    min_tokens: int = 100


@dataclass
class EmbeddingsConfig:
    provider: str = "local"
    model: str = "intfloat/multilingual-e5-small"
    batch_size: int = 64
    device: str = "auto"  # auto | cpu | cuda | mps
    openai_model: str = "text-embedding-3-small"
    openai_api_key_env: str = "OPENAI_API_KEY"


@dataclass
class StoreConfig:
    provider: str = "chroma"
    path: str = "data/profiles/default/chroma"
    collection: str = "default"


@dataclass
class McpConfig:
    server_name: str = "1c-kb"
    transport: str = "stdio"
    host: str = "127.0.0.1"
    port: int = 8301
    default_search_limit: int = 8


@dataclass
class DockerConfig:
    compose_dir: str = ""
    gpu: bool = False  # NVIDIA runtime в compose (опционально)


@dataclass
class DocsConfig:
    enabled: bool = False
    paths: list[str] = field(default_factory=list)


@dataclass
class ProfileConfig:
    """Один профиль = один проект 1С = одна коллекция = один MCP-сервер."""

    profile_name: str
    display_name: str
    format: str
    root: Path
    src: str
    indexing: IndexingConfig
    docs: DocsConfig
    chunking: ChunkingConfig
    embeddings: EmbeddingsConfig
    store: StoreConfig
    mcp: McpConfig
    docker: DockerConfig
    config_path: Path
    project_root: Path = PROJECT_ROOT
    git_branch: str = ""
    watch: WatchConfig = field(default_factory=WatchConfig)
    search: SearchConfig = field(default_factory=SearchConfig)

    @property
    def source_base(self) -> Path:
        if self.format == "edt":
            return self.root / self.src if self.src else self.root
        return self.root


def _parse_indexing(data: dict[str, Any], fmt: str) -> IndexingConfig:
    defaults_include = DEFAULT_EDT_INCLUDE_DIRS if fmt == "edt" else DEFAULT_XML_INCLUDE_DIRS
    defaults_exclude_globs = DEFAULT_EDT_EXCLUDE_GLOBS if fmt == "edt" else DEFAULT_XML_EXCLUDE_GLOBS
    exclude_globs = list(data.get("exclude_globs") or defaults_exclude_globs)
    include_forms = bool(data.get("include_forms", False))
    if include_forms and fmt == "xml_export":
        exclude_globs = [g for g in exclude_globs if g != "**/Forms/**/*.xml"]
    return IndexingConfig(
        include_dirs=data.get("include_dirs") or list(defaults_include),
        exclude_dirs=data.get("exclude_dirs") or list(DEFAULT_EXCLUDE_DIRS),
        exclude_globs=exclude_globs,
        include_forms=include_forms,
    )


def load_config(profile: str | Path | None = None) -> ProfileConfig:
    config_path = resolve_profile_config(profile)
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    profile_meta = raw.get("profile", {})
    project = raw.get("project", {})
    fmt = project.get("format", "edt")
    profile_name = profile_meta.get("name") or config_path.parent.name

    watch_raw = raw.get("watch", {})
    search_raw = raw.get("search", {})
    docs_raw = raw.get("docs", {})
    chunking_raw = raw.get("chunking", {})
    embeddings_raw = raw.get("embeddings", {})
    store_raw = raw.get("store", {})
    mcp_raw = raw.get("mcp", {})
    docker_raw = raw.get("docker", {})

    store_path = store_raw.get("path", f"data/profiles/{profile_name}/chroma")
    collection = store_raw.get("collection", profile_name)

    return ProfileConfig(
        profile_name=profile_name,
        display_name=profile_meta.get("display_name", profile_name),
        format=fmt,
        root=Path(project["root"]).expanduser().resolve(),
        src=project.get("src", "src"),
        indexing=_parse_indexing(raw.get("indexing", {}), fmt),
        watch=WatchConfig(
            enabled=bool(watch_raw.get("enabled", False)),
            mode=str(watch_raw.get("mode", "poll")),
            poll_interval_sec=float(watch_raw.get("poll_interval_sec", 2.0)),
            debounce_sec=float(watch_raw.get("debounce_sec", 3.0)),
        ),
        search=SearchConfig(
            hybrid=bool(search_raw.get("hybrid", True)),
            vector_weight=float(search_raw.get("vector_weight", 0.65)),
            keyword_weight=float(search_raw.get("keyword_weight", 0.35)),
        ),
        docs=DocsConfig(
            enabled=docs_raw.get("enabled", False),
            paths=docs_raw.get("paths", []),
        ),
        chunking=ChunkingConfig(
            target_tokens=chunking_raw.get("target_tokens", 800),
            overlap_ratio=chunking_raw.get("overlap_ratio", 0.12),
            min_tokens=chunking_raw.get("min_tokens", 100),
        ),
        embeddings=EmbeddingsConfig(
            provider=embeddings_raw.get("provider", "local"),
            model=embeddings_raw.get("model", "intfloat/multilingual-e5-small"),
            batch_size=embeddings_raw.get("batch_size", 64),
            device=embeddings_raw.get("device", "auto"),
            openai_model=embeddings_raw.get("openai_model", "text-embedding-3-small"),
            openai_api_key_env=embeddings_raw.get("openai_api_key_env", "OPENAI_API_KEY"),
        ),
        store=StoreConfig(
            provider=store_raw.get("provider", "chroma"),
            path=store_path,
            collection=collection,
        ),
        mcp=McpConfig(
            server_name=mcp_raw.get("server_name", f"1c-kb-{profile_name}"),
            transport=mcp_raw.get("transport", "stdio"),
            host=mcp_raw.get("host", "127.0.0.1"),
            port=mcp_raw.get("port", 8301),
            default_search_limit=mcp_raw.get("default_search_limit", 8),
        ),
        docker=DockerConfig(
            compose_dir=str(docker_raw.get("compose_dir", "") or "").strip(),
            gpu=bool(docker_raw.get("gpu", False)),
        ),
        config_path=config_path,
        git_branch=str(profile_meta.get("git_branch", "") or ""),
    )


# Обратная совместимость для внутренних импортов
AppConfig = ProfileConfig
