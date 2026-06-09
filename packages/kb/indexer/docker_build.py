from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from packages.kb.indexer.docker_manager import PROJECT_ROOT, _get_client
from packages.kb.indexer.docker_names import SHARED_IMAGE_NAME, image_name
from packages.kb.indexer.docker_wheels import ensure_kb_mcp_wheels, resolve_docker_build_platform
from packages.kb.indexer.profiles import slugify
from packages.kb.paths import (
    DEFAULT_PIP_EXTRA_INDEX_URL,
    DEFAULT_PIP_INDEX_URL,
    DEFAULT_PIP_TRUSTED_HOST,
)

DATA_DIR = PROJECT_ROOT / "data" / "docker"


class BuildStatus(str, Enum):
    IDLE = "idle"
    BUILDING = "building"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class DockerBuildState:
    profile_name: str
    status: BuildStatus = BuildStatus.IDLE
    image: str = ""
    shared_image: str = SHARED_IMAGE_NAME
    message: str = ""
    error: str = ""
    log_lines: list[str] = field(default_factory=list)
    force: bool = False

    def __post_init__(self) -> None:
        if not self.image:
            self.image = image_name(self.profile_name)

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "status": self.status.value,
            "image": self.image,
            "shared_image": self.shared_image,
            "message": self.message,
            "error": self.error,
            "log": "\n".join(self.log_lines),
            "force": self.force,
            "image_exists": image_exists(self.profile_name),
            "shared_image_exists": shared_image_exists(),
            "build_history": has_build_history(self.profile_name),
        }


_lock = threading.Lock()
_states: dict[str, DockerBuildState] = {}
_thread: threading.Thread | None = None
_active_build_profile: str | None = None
_orphan_watchers: set[str] = set()


def _normalize_profile(profile_name: str) -> str:
    return slugify(profile_name)


def _profile_data_dir(profile_name: str) -> Path:
    return DATA_DIR / _normalize_profile(profile_name)


def _build_log_path(profile_name: str) -> Path:
    return _profile_data_dir(profile_name) / "build.log"


def _build_meta_path(profile_name: str) -> Path:
    return _profile_data_dir(profile_name) / "build-meta.json"


def _get_state_unlocked(profile_name: str) -> DockerBuildState:
    key = _normalize_profile(profile_name)
    if key not in _states:
        state = DockerBuildState(profile_name=key)
        _states[key] = state
        _load_persisted(key, state)
    return _states[key]


def _persist_state(profile_name: str) -> None:
    state = _get_state_unlocked(profile_name)
    data_dir = _profile_data_dir(profile_name)
    data_dir.mkdir(parents=True, exist_ok=True)
    _build_log_path(profile_name).write_text("\n".join(state.log_lines), encoding="utf-8")
    _build_meta_path(profile_name).write_text(
        json.dumps(
            {
                "status": state.status.value,
                "message": state.message,
                "error": state.error,
                "image": state.image,
                "shared_image": state.shared_image,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _docker_image_exists(ref: str) -> bool:
    try:
        _get_client().images.get(ref)
        return True
    except Exception:
        return False


def shared_image_exists() -> bool:
    return _docker_image_exists(SHARED_IMAGE_NAME)


def tag_profile_image(profile_name: str) -> str:
    """Пометить общий образ тегом профиля (идемпотентно)."""
    profile_image = image_name(profile_name)
    if not shared_image_exists():
        return profile_image
    if _docker_image_exists(profile_image):
        return profile_image
    client = _get_client()
    shared = client.images.get(SHARED_IMAGE_NAME)
    shared.tag(profile_image)
    return profile_image


def image_exists(profile_name: str) -> bool:
    profile_image = image_name(profile_name)
    if _docker_image_exists(profile_image):
        return True
    if shared_image_exists():
        tag_profile_image(profile_name)
        return True
    return False


def _is_external_docker_build_running(image: str) -> bool:
    """docker build мог продолжиться в фоне после перезапуска kb-web."""
    pattern = rf"docker build.*(?:{re.escape(image)}|{re.escape(SHARED_IMAGE_NAME)})"
    try:
        proc = subprocess.run(
            ["pgrep", "-f", pattern],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return proc.returncode == 0
    except Exception:
        return False


def _reconcile_persisted_build_state(profile_name: str, state: DockerBuildState) -> None:
    """Сброс «зависшего» building после перезапуска веб-сервера."""
    if state.status != BuildStatus.BUILDING:
        return
    if _active_build_profile == profile_name:
        return

    if _is_external_docker_build_running(state.image or image_name(profile_name)):
        state.message = "Сборка Docker продолжается в фоне (веб был перезапущен)…"
        if not any("веб был перезапущен" in line for line in state.log_lines):
            state.log_lines.append(
                "⚠ Веб-сервер перезапущен во время сборки. "
                "Лог ниже — до перезапуска; ожидаем завершения docker build…",
            )
        _start_orphan_build_watcher(profile_name)
        _persist_state(profile_name)
        return

    if image_exists(profile_name):
        state.status = BuildStatus.COMPLETED
        state.message = f"Образ {state.image} готов (сборка завершилась в фоне)."
        state.error = ""
        state.log_lines.append("✓ Образ найден после перезапуска веб-сервера — сборка завершена.")
    else:
        state.status = BuildStatus.INTERRUPTED
        state.message = "Сборка прервана при перезапуске веб-сервера"
        state.error = "Процесс сборки остановлен. Запустите «Собрать образ» снова."
        state.log_lines.append(
            "⚠ Сборка прервана: веб-сервер перезапущен, docker build не выполняется. "
            "Нажмите «Собрать образ» (лучше с «Пересобрать»).",
        )
    _persist_state(profile_name)


def _start_orphan_build_watcher(profile_name: str) -> None:
    with _lock:
        if profile_name in _orphan_watchers or _active_build_profile == profile_name:
            return
        _orphan_watchers.add(profile_name)
    threading.Thread(
        target=_watch_orphan_build,
        args=(profile_name,),
        daemon=True,
        name=f"kb-docker-orphan-{profile_name}",
    ).start()


def _watch_orphan_build(profile_name: str) -> None:
    try:
        while _is_external_docker_build_running(image_name(profile_name)):
            time.sleep(5)
        if image_exists(profile_name):
            _set_state(
                profile_name,
                status=BuildStatus.COMPLETED,
                message=f"Образ {image_name(profile_name)} успешно собран.",
                error="",
            )
            _append_log(
                profile_name,
                "✓ Docker build завершился в фоне после перезапуска веб-сервера.",
            )
        else:
            _set_state(
                profile_name,
                status=BuildStatus.INTERRUPTED,
                message="Сборка Docker остановилась без готового образа",
                error="Перезапустите сборку с «Пересобрать образ».",
            )
            _append_log(
                profile_name,
                "⚠ Фоновый docker build завершился с ошибкой или был прерван.",
            )
    finally:
        with _lock:
            _orphan_watchers.discard(profile_name)


def _load_persisted(profile_name: str, state: DockerBuildState) -> None:
    log_path = _build_log_path(profile_name)
    if log_path.exists():
        text = log_path.read_text(encoding="utf-8").strip()
        if text:
            state.log_lines = text.splitlines()
    meta_path = _build_meta_path(profile_name)
    if not meta_path.exists():
        return
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        state.status = BuildStatus(meta.get("status", BuildStatus.IDLE.value))
        state.message = meta.get("message", "")
        state.error = meta.get("error", "")
        state.image = meta.get("image", image_name(profile_name))
        state.shared_image = meta.get("shared_image", SHARED_IMAGE_NAME)
    except Exception:
        pass
    _reconcile_persisted_build_state(profile_name, state)


def get_build_state(profile_name: str) -> DockerBuildState:
    with _lock:
        return _get_state_unlocked(profile_name)


def _append_log(profile_name: str, line: str) -> None:
    line = line.rstrip()
    if not line:
        return
    with _lock:
        state = _get_state_unlocked(profile_name)
        state.log_lines.append(line)
        if len(state.log_lines) > 5000:
            state.log_lines = state.log_lines[-4000:]
    _persist_state(profile_name)


def _set_state(profile_name: str, **kwargs) -> None:
    with _lock:
        state = _get_state_unlocked(profile_name)
        for key, value in kwargs.items():
            setattr(state, key, value)
    _persist_state(profile_name)


def has_build_history(profile_name: str) -> bool:
    """Сборка запускалась через kb-web (есть сохранённый лог или meta)."""
    state = get_build_state(profile_name)
    if state.log_lines:
        return True
    log_path = _build_log_path(profile_name)
    if log_path.exists() and log_path.read_text(encoding="utf-8").strip():
        return True
    return _build_meta_path(profile_name).exists()


def resolve_pip_build_config() -> tuple[str, str, str]:
    """PIP: env → settings.json → PyPI + запасное зеркало по умолчанию."""
    pip_index = os.environ.get("PIP_INDEX_URL", "").strip()
    pip_extra = os.environ.get("PIP_EXTRA_INDEX_URL", "").strip()
    pip_trusted = os.environ.get("PIP_TRUSTED_HOST", "").strip()
    try:
        from web.settings import load_settings

        docker_cfg = load_settings().get("docker") or {}
        pip_index = pip_index or str(docker_cfg.get("pip_index_url") or "").strip()
        pip_extra = pip_extra or str(docker_cfg.get("pip_extra_index_url") or "").strip()
        pip_trusted = pip_trusted or str(docker_cfg.get("pip_trusted_host") or "").strip()
    except Exception:
        pass
    legacy_yandex = "https://mirror.yandex.ru/mirrors/pypi/simple"
    if pip_index.rstrip("/") == legacy_yandex and not pip_extra:
        pip_index = ""
    return (
        pip_index or DEFAULT_PIP_INDEX_URL,
        pip_extra or DEFAULT_PIP_EXTRA_INDEX_URL,
        pip_trusted or DEFAULT_PIP_TRUSTED_HOST,
    )


def pip_ssl_build_hint() -> str:
    return (
        "Подсказка: сбой сети PyPI. Зависимости качаются на хосте, Docker собирается офлайн. "
        "Пересоберите с галочкой «Пересобрать образ». "
        "При ошибке на этапе «Скачивание на хосте» — проверьте интернет/VPN."
    )


def run_docker_build_cli(
    *,
    image: str | None = None,
    dockerfile: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> str:
    """Собрать единый образ KB MCP и вернуть его имя."""
    target_image = image or SHARED_IMAGE_NAME
    dockerfile = dockerfile or PROJECT_ROOT / "packages" / "kb" / "docker" / "Dockerfile"
    if not dockerfile.exists():
        raise FileNotFoundError(f"Dockerfile не найден: {dockerfile}")

    emit = log or (lambda line: None)
    pip_index, _pip_extra, pip_trusted = resolve_pip_build_config()
    trusted_hosts = [h.strip() for h in pip_trusted.split() if h.strip()]

    cmd = [
        "docker",
        "build",
        "--platform",
        resolve_docker_build_platform(),
        "--build-arg",
        f"PIP_INDEX_URL={pip_index}",
        "--build-arg",
        f"PIP_TRUSTED_HOST={' '.join(trusted_hosts) or 'pypi.org'}",
        "-t",
        target_image,
        "-f",
        str(dockerfile),
    ]
    cmd.append(str(PROJECT_ROOT))
    emit(f"$ {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:
        raise RuntimeError("Не удалось запустить docker build")

    for line in proc.stdout:
        emit(line.rstrip("\n"))

    if proc.wait() != 0:
        raise RuntimeError("docker build завершился с ошибкой (см. лог выше)")
    return target_image


def is_building(profile_name: str | None = None) -> bool:
    with _lock:
        if profile_name is not None:
            return _get_state_unlocked(profile_name).status == BuildStatus.BUILDING
        return _active_build_profile is not None


def start_build(profile_name: str, force: bool = False) -> DockerBuildState:
    global _thread, _active_build_profile
    key = _normalize_profile(profile_name)
    with _lock:
        if _active_build_profile is not None:
            raise RuntimeError(
                f"Сборка образа уже выполняется для профиля {_active_build_profile}",
            )
        state = _get_state_unlocked(key)
        if state.status == BuildStatus.BUILDING and _is_external_docker_build_running(
            state.image or image_name(key),
        ):
            raise RuntimeError(
                "Сборка Docker ещё выполняется в фоне. Дождитесь завершения или остановите "
                "docker build в терминале.",
            )
        state.status = BuildStatus.BUILDING
        state.message = "Подготовка…"
        state.error = ""
        state.force = force
        state.image = image_name(key)
        state.shared_image = SHARED_IMAGE_NAME
        if force:
            state.log_lines = []
        _active_build_profile = key

    _persist_state(key)
    _thread = threading.Thread(target=_run_build, args=(key, force), daemon=True)
    _thread.start()
    return get_build_state(key)


def _run_build(profile_name: str, force: bool) -> None:
    global _active_build_profile
    profile_image = image_name(profile_name)
    try:
        if not force and image_exists(profile_name):
            _set_state(
                profile_name,
                status=BuildStatus.SKIPPED,
                message=(
                    f"Образ {profile_image} уже существует. "
                    "Включите «Пересобрать» для новой сборки."
                ),
            )
            _append_log(profile_name, f"✓ Образ {profile_image} найден локально — сборка пропущена.")
            return

        _set_state(profile_name, message="Подготовка wheels на хосте…")
        ensure_kb_mcp_wheels(
            force=force,
            log=lambda line: _append_log(profile_name, line),
        )

        _set_state(profile_name, message="Сборка образа… (5–15 мин)")
        _append_log(profile_name, f"→ Сборка общего образа {SHARED_IMAGE_NAME}")

        run_docker_build_cli(log=lambda line: _append_log(profile_name, line))

        tagged = tag_profile_image(profile_name)
        _set_state(
            profile_name,
            status=BuildStatus.COMPLETED,
            message=f"Образ {tagged} готов (общий {SHARED_IMAGE_NAME}).",
        )
        _append_log(profile_name, f"✓ Готово: {SHARED_IMAGE_NAME} → {tagged}")
    except Exception as exc:
        _set_state(
            profile_name,
            status=BuildStatus.FAILED,
            message="Ошибка сборки образа",
            error=str(exc),
        )
        _append_log(profile_name, traceback.format_exc())
        state = _get_state_unlocked(profile_name)
        log_text = "\n".join(state.log_lines)
        if "SSLError" in log_text or "UNEXPECTED_EOF_WHILE_READING" in log_text:
            _append_log(profile_name, pip_ssl_build_hint())
    finally:
        with _lock:
            _active_build_profile = None
