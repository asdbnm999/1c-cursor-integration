"""Экспорт и импорт архива индекса (Chroma + manifest + config snapshot)."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from packages.kb.indexer.config import ProfileConfig, load_config
from packages.kb.indexer.embeddings import get_embedding_dimension
from packages.kb.indexer.exceptions import ArchiveError, ProfileNotFoundError
from packages.kb.indexer.index_state import manifest_path
from packages.kb.indexer.profiles import (
    PROJECT_ROOT,
    allocate_http_port,
    default_mcp_server_name,
    profile_config_path,
    profile_dir,
)
from packages.kb.indexer.store import _resolve_store_path, reset_store_cache

ARCHIVE_SCHEMA_VERSION = 1


def _compose_dir_matches_profile(compose_dir: str, profile_name: str) -> bool:
    value = (compose_dir or "").strip()
    if not value:
        return True
    return f"1c-kb-{profile_name}" in value.replace("\\", "/")


def _needs_identity_remap(raw: dict, profile_name: str) -> bool:
    expected_server = default_mcp_server_name(profile_name)
    actual_server = str((raw.get("mcp") or {}).get("server_name") or "").strip()
    if actual_server and actual_server != expected_server:
        return True
    compose_dir = str((raw.get("docker") or {}).get("compose_dir") or "").strip()
    return not _compose_dir_matches_profile(compose_dir, profile_name)


def _remap_profile_docker_identity(raw: dict, profile_name: str) -> None:
    raw.setdefault("mcp", {})
    raw.setdefault("docker", {})
    raw["mcp"]["server_name"] = default_mcp_server_name(profile_name)
    raw["mcp"]["port"] = allocate_http_port(profile_name)
    raw["docker"]["compose_dir"] = ""


def repair_imported_profile_identity(profile_name: str) -> bool:
    """Приводит MCP/Docker-имена к текущему профилю (после импорта под другим именем)."""
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        return False
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if str((raw.get("profile") or {}).get("name") or "").strip() != profile_name:
        return False
    if not _needs_identity_remap(raw, profile_name):
        return False
    _remap_profile_docker_identity(raw, profile_name)
    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return True


def _validate_tar_members(tar: tarfile.TarFile, dest: Path) -> None:
    dest_resolved = dest.resolve()
    for member in tar.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest_resolved)):
            raise ArchiveError(
                "Небезопасный путь в архиве (path traversal)",
                details=member.name,
            )


def _safe_extract(tar: tarfile.TarFile, dest: Path) -> None:
    _validate_tar_members(tar, dest)
    tar.extractall(dest, filter="data")


def _open_tar_archive(archive_path: Path) -> tarfile.TarFile:
    """Открывает .tar.gz или .tar (в т.ч. если браузер распаковал gzip при скачивании)."""
    try:
        return tarfile.open(archive_path, "r:*")
    except tarfile.TarError as exc:
        raise ArchiveError("Не удалось распаковать архив", details=str(exc)) from exc


def export_index(profile_name: str, output_path: Path | None = None) -> Path:
    """Упаковывает chroma, manifest и config.yaml в .tar.gz."""
    config_path = profile_config_path(profile_name)
    if not config_path.exists():
        raise ProfileNotFoundError(f"Профиль не найден: {profile_name}")

    config = load_config(profile_name)
    store_path = _resolve_store_path(config)
    if not store_path.exists():
        raise ArchiveError("Индекс пуст — нечего экспортировать", details=str(store_path))

    if output_path is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = PROJECT_ROOT / "data" / "exports" / f"{profile_name}-{ts}.tar.gz"
    output_path = Path(output_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        embedding_dim = get_embedding_dimension(config.embeddings)
    except Exception:
        embedding_dim = 0

    meta = {
        "schema_version": ARCHIVE_SCHEMA_VERSION,
        "profile_name": profile_name,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "collection": config.store.collection,
        "embeddings": {
            "provider": config.embeddings.provider,
            "model": config.embeddings.model,
            "openai_model": config.embeddings.openai_model,
            "embedding_dim": embedding_dim,
        },
        "chunks_hint": _safe_count(config),
    }

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            staging = tmp_path / profile_name
            staging.mkdir()
            (staging / "config.yaml").write_text(
                config_path.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            (staging / "archive-meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            shutil.copytree(store_path, staging / "chroma", dirs_exist_ok=True)
            mpath = manifest_path(config)
            if mpath.exists():
                shutil.copy2(mpath, staging / "index-manifest.json")

            with tarfile.open(output_path, "w:gz") as tar:
                tar.add(staging, arcname=profile_name)
    except OSError as exc:
        raise ArchiveError("Не удалось создать архив", details=str(exc)) from exc

    return output_path


def _validate_import_embeddings(meta: dict, config: ProfileConfig) -> None:
    emb_meta = meta.get("embeddings") or {}
    archive_dim = int(emb_meta.get("embedding_dim") or 0)
    if archive_dim <= 0:
        return
    try:
        local_dim = get_embedding_dimension(config.embeddings)
    except Exception as exc:
        raise ArchiveError(
            "Не удалось проверить размерность эмбеддингов",
            details=str(exc),
        ) from exc
    if local_dim != archive_dim:
        raise ArchiveError(
            "Несовпадение размерности эмбеддингов",
            details=f"архив: {archive_dim}, локально: {local_dim}. "
            "Используйте ту же модель embeddings или выполните полную переиндексацию",
        )


def import_index(
    archive_path: Path | str,
    *,
    target_profile: str | None = None,
    overwrite: bool = False,
) -> str:
    """Восстанавливает индекс из .tar.gz. Возвращает имя профиля."""
    archive_path = Path(archive_path).expanduser().resolve()
    if not archive_path.is_file():
        raise ArchiveError("Файл архива не найден", details=str(archive_path))

    try:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with _open_tar_archive(archive_path) as tar:
                _safe_extract(tar, tmp_path)

            roots = [p for p in tmp_path.iterdir() if p.is_dir()]
            if not roots:
                raise ArchiveError("Архив пуст или повреждён")
            staging = roots[0]

            meta_file = staging / "archive-meta.json"
            meta = json.loads(meta_file.read_text(encoding="utf-8")) if meta_file.exists() else {}
            schema = int(meta.get("schema_version") or 0)
            if schema and schema > ARCHIVE_SCHEMA_VERSION:
                raise ArchiveError(
                    "Версия архива новее приложения",
                    details=f"schema_version={schema}",
                )

            archive_profile_name = meta.get("profile_name") or staging.name
            profile_name = target_profile or archive_profile_name
            renamed = profile_name != archive_profile_name

            src_config = staging / "config.yaml"
            src_raw = yaml.safe_load(src_config.read_text(encoding="utf-8")) if src_config.exists() else {}
            original_collection = meta.get("collection") or src_raw.get("store", {}).get("collection") or profile_name

            dest_profile = profile_dir(profile_name)
            dest_config = profile_config_path(profile_name)
            if dest_config.exists() and not overwrite:
                raise ArchiveError(
                    f"Профиль '{profile_name}' уже существует",
                    details="Укажите overwrite=true или другое имя",
                )

            dest_profile.mkdir(parents=True, exist_ok=True)
            if src_config.exists():
                raw = dict(src_raw)
                raw.setdefault("profile", {})["name"] = profile_name
                raw.setdefault("store", {})["collection"] = original_collection
                raw.setdefault("store", {})["path"] = f"data/profiles/{profile_name}/chroma"
                if renamed or _needs_identity_remap(raw, profile_name):
                    _remap_profile_docker_identity(raw, profile_name)
                dest_config.write_text(
                    yaml.dump(raw, allow_unicode=True, sort_keys=False),
                    encoding="utf-8",
                )

            config = load_config(profile_name)
            _validate_import_embeddings(meta, config)

            store_dest = _resolve_store_path(config)
            if store_dest.exists():
                shutil.rmtree(store_dest)
            chroma_src = staging / "chroma"
            if chroma_src.exists():
                shutil.copytree(chroma_src, store_dest)
            else:
                raise ArchiveError("В архиве нет каталога chroma")

            manifest_src = staging / "index-manifest.json"
            if manifest_src.exists():
                mdest = manifest_path(config)
                mdest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(manifest_src, mdest)

            reset_store_cache()
    except tarfile.TarError as exc:
        raise ArchiveError("Не удалось распаковать архив", details=str(exc)) from exc
    except ArchiveError:
        raise
    except Exception as exc:
        raise ArchiveError("Ошибка импорта", details=str(exc)) from exc

    return profile_name


def _safe_count(config: ProfileConfig) -> int:
    try:
        from packages.kb.indexer.store import count_chunks
        return count_chunks(config)
    except Exception:
        return 0
