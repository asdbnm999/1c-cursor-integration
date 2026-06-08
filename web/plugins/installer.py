"""Установка VSIX: CLI cursor или ручная распаковка (ТЗ §9.4–9.5)."""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from web.plugins.paths import find_cursor_cli, resolve_extensions_dir
from web.plugins.vsix import (
    InstalledExtension,
    VsixMeta,
    compare_versions,
    read_vsix_meta,
    scan_installed_extensions,
)


@dataclass
class InstallResult:
    path: str
    status: str  # ok | skipped | failed | conflict
    message: str
    extension_id: str | None = None
    version: str | None = None
    method: str | None = None
    needs_force: bool = False


def _install_via_cli(cli: str, vsix_path: Path, *, force: bool) -> tuple[bool, str]:
    cmd = [cli, "--install-extension", str(vsix_path)]
    if force:
        cmd.append("--force")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        return False, stderr or f"cursor завершился с кодом {result.returncode}"
    return True, "Установлено через cursor CLI"


def _remove_other_versions(meta: VsixMeta, target_dir: Path, keep: Path) -> None:
    prefix = f"{meta.extension_id}-"
    for entry in target_dir.iterdir():
        if not entry.is_dir() or entry == keep:
            continue
        if entry.name.startswith(prefix):
            shutil.rmtree(entry, ignore_errors=True)


def _install_manual(meta: VsixMeta, target_dir: Path) -> tuple[bool, str]:
    dest = target_dir / meta.folder_name
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(meta.path) as archive:
            for member in archive.namelist():
                if not member.startswith("extension/"):
                    continue
                relative = member[len("extension/") :]
                if not relative or relative.endswith("/"):
                    continue
                out_path = dest / relative
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, out_path.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
    except (OSError, zipfile.BadZipFile, KeyError) as exc:
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        return False, f"Ошибка распаковки: {exc}"
    _remove_other_versions(meta, target_dir, dest)
    return True, f"Распаковано в {dest}"


def _evaluate_before_install(
    meta: VsixMeta,
    installed: dict[str, InstalledExtension],
    *,
    force: bool,
) -> InstallResult | None:
    current = installed.get(meta.extension_id)
    if current is None:
        return None
    if compare_versions(meta.version, current.version) == 0:
        return InstallResult(
            path=str(meta.path),
            status="skipped",
            message="Уже установлено",
            extension_id=meta.extension_id,
            version=current.version,
        )
    if not force:
        return InstallResult(
            path=str(meta.path),
            status="conflict",
            message=(
                f"Установлена версия v{current.version}, в VSIX — v{meta.version}. "
                "Подтвердите переустановку."
            ),
            extension_id=meta.extension_id,
            version=meta.version,
            needs_force=True,
        )
    return None


def install_vsix(vsix_path: Path, *, force: bool = False) -> InstallResult:
    """Установить один VSIX."""
    try:
        meta = read_vsix_meta(vsix_path)
    except (OSError, ValueError) as exc:
        return InstallResult(path=str(vsix_path), status="failed", message=str(exc))

    target_dir, source = resolve_extensions_dir()
    if target_dir is None:
        return InstallResult(
            path=str(meta.path),
            status="failed",
            message="Укажите каталог расширений Cursor вручную",
        )
    if not target_dir.is_dir():
        return InstallResult(
            path=str(meta.path),
            status="failed",
            message=(
                f"Каталог расширений не существует: {target_dir}. "
                "Укажите каталог вручную или установите Cursor."
            ),
        )

    installed = scan_installed_extensions(target_dir)
    preflight = _evaluate_before_install(meta, installed, force=force)
    if preflight is not None:
        return preflight

    cli = find_cursor_cli()
    if cli:
        ok, msg = _install_via_cli(cli, meta.path, force=force)
        if ok:
            return InstallResult(
                path=str(meta.path),
                status="ok",
                message=msg,
                extension_id=meta.extension_id,
                version=meta.version,
                method="cli",
            )
        # fallback manual если CLI не сработал

    ok, msg = _install_manual(meta, target_dir)
    if not ok:
        return InstallResult(path=str(meta.path), status="failed", message=msg)
    return InstallResult(
        path=str(meta.path),
        status="ok",
        message=msg,
        extension_id=meta.extension_id,
        version=meta.version,
        method="manual",
    )


def install_batch(paths: list[str], *, force: bool = False) -> list[InstallResult]:
    results: list[InstallResult] = []
    for raw in paths:
        results.append(install_vsix(Path(raw), force=force))
    return results


def record_installed_entries(results: list[InstallResult]) -> list[dict]:
    """Записи для settings.plugins.installed[]."""
    now = datetime.now(UTC).isoformat()
    entries: list[dict] = []
    for item in results:
        if item.status != "ok" or not item.extension_id:
            continue
        entries.append(
            {
                "extension_id": item.extension_id,
                "version": item.version,
                "vsix_path": item.path,
                "installed_at": now,
                "method": item.method or "unknown",
            }
        )
    return entries
