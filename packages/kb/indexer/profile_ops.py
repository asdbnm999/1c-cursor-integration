from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from packages.kb.indexer.constants import (
    DEFAULT_EDT_EXCLUDE_GLOBS,
    DEFAULT_EDT_INCLUDE_DIRS,
    DEFAULT_EXCLUDE_DIRS,
    DEFAULT_XML_EXCLUDE_GLOBS,
    DEFAULT_XML_INCLUDE_DIRS,
)
from packages.kb.indexer.git_changes import get_git_branch
from packages.kb.indexer.profiles import (
    PROJECT_ROOT,
    PROFILES_DIR,
    allocate_http_port,
    profile_config_path,
    profile_dir,
    slugify,
)

TEMPLATE_PATH = PROFILES_DIR / "_template" / "config.yaml"


def create_profile(
    *,
    name: str,
    display_name: str,
    fmt: str,
    root: str | Path,
    src: str = "src",
    port: int = 0,
    docs_enabled: bool = True,
    docs_paths: list[str] | None = None,
    include_forms: bool = False,
) -> Path:
    profile_name = slugify(name)
    config_path = profile_config_path(profile_name)
    if config_path.exists():
        raise FileExistsError(f"Профиль уже существует: {profile_name}")

    data_path = PROJECT_ROOT / "data" / "profiles" / profile_name
    if data_path.exists():
        shutil.rmtree(data_path)

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Путь не найден: {root_path}")

    if fmt == "edt":
        src_path = root_path / src
        if not src_path.exists():
            raise FileNotFoundError(f"EDT src не найден: {src_path}")

    display = display_name or profile_name
    http_port = port or allocate_http_port(profile_name)
    docs_paths = docs_paths if docs_paths is not None else (["docs"] if docs_enabled else [])

    if not TEMPLATE_PATH.exists():
        raise FileNotFoundError(f"Шаблон не найден: {TEMPLATE_PATH}")

    content = (
        TEMPLATE_PATH.read_text(encoding="utf-8")
        .replace("PROFILE_NAME", profile_name)
        .replace("DISPLAY_NAME", display)
        .replace("format: edt", f"format: {fmt}")
        .replace("root: /path/to/project", f"root: {root_path}")
        .replace(
            "src: src                 # только для edt; для xml_export оставьте пустым или удалите",
            f"src: {src}" if fmt == "edt" else 'src: ""',
        )
        .replace("enabled: true", f"enabled: {str(docs_enabled).lower()}")
        .replace("include_forms: false", f"include_forms: {str(include_forms).lower()}")
        .replace("transport: http", "transport: http")
        .replace("port: 8010", f"port: {http_port}")
    )

    if docs_paths:
        paths_yaml = "\n".join(f'    - "{p}"' for p in docs_paths)
        content = content.replace("paths:\n    - docs", f"paths:\n{paths_yaml}")

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content, encoding="utf-8")

    branch = get_git_branch(root_path)
    if branch:
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle) or {}
        raw.setdefault("profile", {})["git_branch"] = branch
        config_path.write_text(
            yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
            encoding="utf-8",
        )

    store_dir = PROJECT_ROOT / "data" / "profiles" / profile_name / "chroma"
    store_dir.mkdir(parents=True, exist_ok=True)

    return config_path


def ensure_default_compose_dir(profile_name: str) -> str | None:
    """Записать стандартную compose-директорию, если в профиле она ещё не задана."""
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        return None
    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    existing = str((raw.get("docker") or {}).get("compose_dir") or "").strip()
    if existing:
        return existing
    from packages.kb.indexer.docker_compose import default_compose_dir

    target = save_compose_dir(profile_name, default_compose_dir(profile_name))
    return str(target)


def save_docker_mem_limit(profile_name: str, mem_limit_mb: int) -> int:
    from packages.kb.indexer.docker_compose import KB_MEM_LIMIT_UI

    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    lo = int(KB_MEM_LIMIT_UI["min"])
    hi = int(KB_MEM_LIMIT_UI["max"])
    value = max(lo, min(hi, int(mem_limit_mb)))

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    raw.setdefault("docker", {})
    raw["docker"]["mem_limit_mb"] = value
    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return value


def save_compose_dir(profile_name: str, compose_dir: str | Path) -> Path:
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    target = Path(compose_dir).expanduser().resolve()
    target.mkdir(parents=True, exist_ok=True)

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    raw.setdefault("docker", {})
    raw["docker"]["compose_dir"] = str(target)
    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return target


def delete_profile(profile_name: str) -> None:
    """Удаляет только каталог конфигурации profiles/<имя> (для тестов)."""
    path = profile_dir(profile_name)
    if path.exists():
        import shutil
        shutil.rmtree(path)


def delete_profile_completely(profile_name: str) -> dict[str, bool]:
    """Удаляет профиль и все связанные данные: Chroma, data/, Docker, watch."""
    import shutil

    from packages.kb.indexer.jobs import clear_profile_jobs
    from packages.kb.indexer.store import reset_store_cache

    result = {
        "profile_config": False,
        "data_dir": False,
        "docker_stopped": False,
        "watch_stopped": False,
        "mcp_removed": False,
    }

    try:
        from packages.kb.indexer.watcher import stop_watch

        stop_watch(profile_name)
        result["watch_stopped"] = True
    except Exception:
        pass

    clear_profile_jobs(profile_name)

    try:
        from packages.kb.indexer.cursor_mcp_config import remove_profile_from_cursor_mcp

        config = load_config(profile_name)
        remove_result = remove_profile_from_cursor_mcp(config)
        result["mcp_removed"] = bool(remove_result.get("removed"))
    except Exception:
        pass

    try:
        config = load_config(profile_name)
        compose_dir = (config.docker.compose_dir or "").strip()
        if compose_dir:
            from packages.kb.indexer.docker_compose import compose_down

            compose_down(Path(compose_dir).expanduser(), profile_name)
    except Exception:
        pass

    try:
        from packages.kb.indexer.docker_manager import remove_container, stop_container

        stop_container(profile_name)
        remove_container(profile_name)
        result["docker_stopped"] = True
    except Exception:
        pass

    cfg_path = profile_dir(profile_name)
    if cfg_path.exists():
        shutil.rmtree(cfg_path)
        result["profile_config"] = True

    data_path = PROJECT_ROOT / "data" / "profiles" / profile_name
    if data_path.exists():
        shutil.rmtree(data_path)
        result["data_dir"] = True

    docker_build_path = PROJECT_ROOT / "data" / "docker" / slugify(profile_name)
    if docker_build_path.exists():
        shutil.rmtree(docker_build_path)

    reset_store_cache()
    return result


def load_profile_meta(profile_name: str) -> dict:
    config_path = profile_config_path(profile_name)
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def save_embeddings_settings(
    profile_name: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    device: str | None = None,
    batch_size: int | None = None,
) -> dict:
    """Обновляет настройки embeddings в config.yaml профиля."""
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    emb = raw.setdefault("embeddings", {})
    old_model = emb.get("model")
    old_provider = emb.get("provider")
    if provider is not None:
        emb["provider"] = provider
    if model is not None:
        emb["model"] = model
    if device is not None:
        emb["device"] = device
    if batch_size is not None:
        emb["batch_size"] = batch_size

    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    from packages.kb.indexer.embeddings import clear_model_cache
    clear_model_cache()
    needs_reindex = (
        (model is not None and model != old_model)
        or (provider is not None and provider != old_provider)
    )
    emb["needs_reindex"] = needs_reindex
    return emb


def save_watch_settings(
    profile_name: str,
    *,
    enabled: bool | None = None,
    mode: str | None = None,
    poll_interval_sec: float | None = None,
    debounce_sec: float | None = None,
) -> dict:
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    watch = raw.setdefault("watch", {})
    if enabled is not None:
        watch["enabled"] = enabled
    if mode is not None:
        watch["mode"] = mode
    if poll_interval_sec is not None:
        watch["poll_interval_sec"] = poll_interval_sec
    if debounce_sec is not None:
        watch["debounce_sec"] = debounce_sec

    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return watch


def save_indexing_settings(profile_name: str, *, include_forms: bool | None = None) -> dict:
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    idx = raw.setdefault("indexing", {})
    old_include_forms = idx.get("include_forms", False)
    if include_forms is not None:
        idx["include_forms"] = include_forms

    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    idx["needs_reindex"] = include_forms is not None and include_forms != old_include_forms
    return idx


def _profile_data_dir(profile_name: str) -> Path:
    return PROJECT_ROOT / "data" / "profiles" / profile_name


def _copy_profile_index_data(source_name: str, target_name: str) -> None:
    """Копирует chroma, manifest и вспомогательные индексы."""
    src = _profile_data_dir(source_name)
    dest = _profile_data_dir(target_name)
    dest.mkdir(parents=True, exist_ok=True)

    chroma_src = src / "chroma"
    if not chroma_src.exists() or not any(chroma_src.iterdir()):
        raise FileNotFoundError(f"Индекс источника пуст: {source_name}")

    chroma_dest = dest / "chroma"
    if chroma_dest.exists():
        shutil.rmtree(chroma_dest)
    shutil.copytree(chroma_src, chroma_dest)

    for name in ("index-manifest.json", "metadata-snapshot.json"):
        src_file = src / name
        if src_file.is_file():
            shutil.copy2(src_file, dest / name)

    indexes_src = src / "indexes"
    if indexes_src.is_dir():
        indexes_dest = dest / "indexes"
        if indexes_dest.exists():
            shutil.rmtree(indexes_dest)
        shutil.copytree(indexes_src, indexes_dest)


def clone_profile(
    source_name: str,
    target_name: str,
    *,
    display_name: str = "",
    root: str | Path | None = None,
    copy_index: bool = False,
    git_branch: str = "",
) -> Path:
    """Клонирует профиль для ветки/релиза (новая коллекция, тот же или другой root)."""
    src_path = profile_config_path(source_name)
    if not src_path.exists():
        raise FileNotFoundError(f"Исходный профиль не найден: {source_name}")

    target = slugify(target_name)
    dest_path = profile_config_path(target)
    if dest_path.exists():
        raise FileExistsError(f"Целевой профиль уже существует: {target}")

    with src_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}

    source_collection = raw.get("store", {}).get("collection", source_name)

    raw.setdefault("profile", {})["name"] = target
    raw["profile"]["display_name"] = display_name or f"{raw['profile'].get('display_name', target)} ({target})"
    raw.setdefault("store", {})["path"] = f"data/profiles/{target}/chroma"
    raw["store"]["collection"] = source_collection if copy_index else target
    project_root = Path(raw.get("project", {}).get("root", "")).expanduser()
    if root is not None:
        project_root = Path(root).expanduser().resolve()
        raw.setdefault("project", {})["root"] = str(project_root)

    branch = git_branch or get_git_branch(project_root)
    if branch:
        raw.setdefault("profile", {})["git_branch"] = branch

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    dest_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )

    if copy_index:
        _copy_profile_index_data(source_name, target)
        from packages.kb.indexer.store import reset_store_cache
        reset_store_cache()
    else:
        store_dir = PROJECT_ROOT / "data" / "profiles" / target / "chroma"
        store_dir.mkdir(parents=True, exist_ok=True)
    return dest_path


def get_default_indexing(fmt: str) -> dict:
    if fmt == "edt":
        return {
            "include_dirs": list(DEFAULT_EDT_INCLUDE_DIRS),
            "exclude_dirs": list(DEFAULT_EXCLUDE_DIRS),
            "exclude_globs": list(DEFAULT_EDT_EXCLUDE_GLOBS),
        }
    return {
        "include_dirs": list(DEFAULT_XML_INCLUDE_DIRS),
        "exclude_dirs": list(DEFAULT_EXCLUDE_DIRS),
        "exclude_globs": list(DEFAULT_XML_EXCLUDE_GLOBS),
    }
