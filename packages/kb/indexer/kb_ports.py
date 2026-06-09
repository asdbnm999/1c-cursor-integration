"""Порты MCP профилей KB (диапазон 83xx, ТЗ §7.1)."""

from __future__ import annotations

import yaml

from packages.kb.indexer.profiles import list_profiles, profile_config_path

KB_PORT_MIN = 8301
KB_PORT_MAX = 8399


def is_kb_port(port: int) -> bool:
    return KB_PORT_MIN <= port <= KB_PORT_MAX


def _reserved_kb_ports(*, exclude_profile: str | None = None) -> set[int]:
    """Порты, назначенные другим профилям KB в config.yaml."""
    reserved: set[int] = set()
    for name in list_profiles():
        if exclude_profile and name == exclude_profile:
            continue
        path = profile_config_path(name)
        if not path.is_file():
            continue
        try:
            with path.open(encoding="utf-8") as handle:
                raw = yaml.safe_load(handle) or {}
            port = int((raw.get("mcp") or {}).get("port") or 0)
            if is_kb_port(port):
                reserved.add(port)
        except (OSError, TypeError, ValueError):
            continue
    return reserved


def find_free_kb_port(
    *,
    exclude_profile: str | None = None,
    preferred: int | None = None,
) -> int:
    """Первый свободный порт в 8301–8399 (сначала preferred, затем по возрастанию)."""
    from web.system_check import is_port_free

    reserved = _reserved_kb_ports(exclude_profile=exclude_profile)
    order: list[int] = []
    if preferred is not None and is_kb_port(preferred):
        order.append(preferred)
    for port in range(KB_PORT_MIN, KB_PORT_MAX + 1):
        if port not in order:
            order.append(port)

    for port in order:
        if port in reserved:
            continue
        if is_port_free(port):
            return port

    raise RuntimeError(
        f"Нет свободных портов в диапазоне {KB_PORT_MIN}–{KB_PORT_MAX}. "
        "Остановите лишние MCP-контейнеры или освободите порт вручную."
    )


def save_mcp_port(profile_name: str, port: int) -> None:
    """Записать mcp.port в config.yaml профиля."""
    if not is_kb_port(port):
        raise ValueError(f"Порт {port} вне диапазона KB {KB_PORT_MIN}–{KB_PORT_MAX}")

    config_path = profile_config_path(profile_name)
    if not config_path.is_file():
        raise FileNotFoundError(f"Профиль не найден: {profile_name}")

    with config_path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle) or {}
    raw.setdefault("mcp", {})
    raw["mcp"]["port"] = int(port)
    config_path.write_text(
        yaml.dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


def ensure_profile_host_port(profile_name: str) -> tuple[int, bool]:
    """
    Вернуть рабочий host port для профиля.
    Если текущий занят — выбрать первый свободный в 8301–8399 и сохранить в config.
    """
    from packages.kb.indexer.config import load_config

    config = load_config(profile_name)
    current = int(config.mcp.port)
    reserved = _reserved_kb_ports(exclude_profile=profile_name)

    from web.system_check import is_port_free

    if is_kb_port(current) and current not in reserved and is_port_free(current):
        return current, False

    preferred = current if is_kb_port(current) else KB_PORT_MIN
    new_port = find_free_kb_port(exclude_profile=profile_name, preferred=preferred)
    if new_port != current:
        save_mcp_port(profile_name, new_port)
    return new_port, new_port != current
