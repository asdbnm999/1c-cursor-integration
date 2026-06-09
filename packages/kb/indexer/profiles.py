from __future__ import annotations

import re
from pathlib import Path

from packages.kb.paths import DATA_PROFILES_DIR, PROFILES_DIR, PROJECT_ROOT

DATA_DIR = DATA_PROFILES_DIR


def slugify(name: str) -> str:
    value = name.strip().lower()
    value = re.sub(r"[^\w\-]+", "-", value, flags=re.UNICODE)
    value = re.sub(r"-{2,}", "-", value).strip("-")
    return value or "profile"


def list_profiles() -> list[str]:
    if not PROFILES_DIR.exists():
        return []
    result: list[str] = []
    for path in sorted(PROFILES_DIR.iterdir()):
        if path.is_dir() and (path / "config.yaml").exists() and not path.name.startswith("_"):
            result.append(path.name)
    return result


def profile_dir(profile_name: str) -> Path:
    return PROFILES_DIR / profile_name


def profile_config_path(profile_name: str) -> Path:
    return profile_dir(profile_name) / "config.yaml"


def resolve_profile_config(profile: str | Path | None = None) -> Path:
    if profile is None:
        profiles = list_profiles()
        if len(profiles) == 1:
            return profile_config_path(profiles[0])
        if not profiles:
            raise FileNotFoundError(
                "Профили не найдены. Создайте: python scripts/create_profile.py --help"
            )
        raise ValueError(
            f"Укажите --profile. Доступны: {', '.join(profiles)}"
        )
    path = Path(profile)
    if path.is_file():
        return path.resolve()
    config = profile_config_path(str(profile))
    if not config.exists():
        raise FileNotFoundError(f"Профиль не найден: {config}")
    return config.resolve()


def default_store_path(profile_name: str) -> str:
    return f"data/profiles/{profile_name}/chroma"


def default_mcp_server_name(profile_name: str) -> str:
    return f"1c-kb-{profile_name}"


def allocate_http_port(profile_name: str) -> int:
    """Предпочтительный порт по индексу профиля; при занятости — сканирование 8301–8399."""
    from packages.kb.indexer.kb_ports import find_free_kb_port

    base = 8301
    existing = list_profiles()
    if profile_name in existing:
        preferred = base + existing.index(profile_name)
    else:
        preferred = base + len(existing)
    preferred = min(preferred, 8399)
    return find_free_kb_port(exclude_profile=profile_name, preferred=preferred)
