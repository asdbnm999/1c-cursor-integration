from __future__ import annotations

import json
import os
import subprocess
import threading
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from packages.kb.indexer.docker_manager import PROJECT_ROOT, _get_client
from packages.kb.indexer.docker_names import image_name
from packages.kb.indexer.profiles import slugify

DATA_DIR = PROJECT_ROOT / "data" / "docker"


class BuildStatus(str, Enum):
    IDLE = "idle"
    BUILDING = "building"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass
class DockerBuildState:
    profile_name: str
    status: BuildStatus = BuildStatus.IDLE
    image: str = ""
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
            "message": self.message,
            "error": self.error,
            "log": "\n".join(self.log_lines),
            "force": self.force,
            "image_exists": image_exists(self.profile_name),
            "build_history": has_build_history(self.profile_name),
        }


_lock = threading.Lock()
_states: dict[str, DockerBuildState] = {}
_thread: threading.Thread | None = None
_active_build_profile: str | None = None


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
        _load_persisted(key, state)
        _states[key] = state
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
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


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
    except Exception:
        pass


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


def image_exists(profile_name: str) -> bool:
    image = image_name(profile_name)
    try:
        _get_client().images.get(image)
        return True
    except Exception:
        return False


def has_build_history(profile_name: str) -> bool:
    """Сборка запускалась через kb-web (есть сохранённый лог или meta)."""
    state = get_build_state(profile_name)
    if state.log_lines:
        return True
    log_path = _build_log_path(profile_name)
    if log_path.exists() and log_path.read_text(encoding="utf-8").strip():
        return True
    return _build_meta_path(profile_name).exists()


def resolve_pip_build_config() -> tuple[str, str]:
    """PIP mirror для docker build: env → data/settings.json → docker.pip_*."""
    pip_index = os.environ.get("PIP_INDEX_URL", "").strip()
    pip_trusted = os.environ.get("PIP_TRUSTED_HOST", "").strip()
    if pip_index and pip_trusted:
        return pip_index, pip_trusted
    try:
        from web.settings import load_settings

        docker_cfg = load_settings().get("docker") or {}
        pip_index = pip_index or str(docker_cfg.get("pip_index_url") or "").strip()
        pip_trusted = pip_trusted or str(docker_cfg.get("pip_trusted_host") or "").strip()
    except Exception:
        pass
    return pip_index, pip_trusted


def pip_ssl_build_hint() -> str:
    return (
        "Подсказка: SSL-ошибки PyPI в Docker — задайте зеркало в data/settings.json:\n"
        '  "docker": { "pip_index_url": "https://mirror.yandex.ru/mirrors/pypi/simple/", '
        '"pip_trusted_host": "mirror.yandex.ru" }\n'
        "или экспортируйте PIP_INDEX_URL / PIP_TRUSTED_HOST перед сборкой. "
        "Также отключите VPN/фильтр HTTPS на время сборки."
    )


def run_docker_build_cli(
    *,
    image: str,
    dockerfile: Path | None = None,
    log: Callable[[str], None] | None = None,
) -> None:
    dockerfile = dockerfile or PROJECT_ROOT / "packages" / "kb" / "docker" / "Dockerfile"
    if not dockerfile.exists():
        raise FileNotFoundError(f"Dockerfile не найден: {dockerfile}")

    emit = log or (lambda line: None)
    cmd = [
        "docker",
        "build",
        "-t",
        image,
        "-f",
        str(dockerfile),
    ]
    pip_index, pip_trusted = resolve_pip_build_config()
    if pip_index:
        cmd.extend(["--build-arg", f"PIP_INDEX_URL={pip_index}"])
    if pip_trusted:
        cmd.extend(["--build-arg", f"PIP_TRUSTED_HOST={pip_trusted}"])
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
        state.status = BuildStatus.BUILDING
        state.message = "Подготовка…"
        state.error = ""
        state.force = force
        state.image = image_name(key)
        if force:
            state.log_lines = []
        _active_build_profile = key

    _persist_state(key)
    _thread = threading.Thread(target=_run_build, args=(key, force), daemon=True)
    _thread.start()
    return get_build_state(key)


def _run_build(profile_name: str, force: bool) -> None:
    global _active_build_profile
    image = image_name(profile_name)
    try:
        if not force and image_exists(profile_name):
            _set_state(
                profile_name,
                status=BuildStatus.SKIPPED,
                message=f"Образ {image} уже существует. Включите «Пересобрать» для новой сборки.",
            )
            _append_log(profile_name, f"✓ Образ {image} найден локально — сборка пропущена.")
            return

        _set_state(profile_name, message="Сборка образа… (10–20 мин при первом запуске)")
        _append_log(profile_name, f"→ Сборка {image}")

        run_docker_build_cli(image=image, log=lambda line: _append_log(profile_name, line))

        _set_state(
            profile_name,
            status=BuildStatus.COMPLETED,
            message=f"Образ {image} успешно собран.",
        )
        _append_log(profile_name, f"✓ Готово: {image}")
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
