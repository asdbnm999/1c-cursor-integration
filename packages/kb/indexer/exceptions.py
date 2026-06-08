"""Иерархия исключений индексатора с понятными сообщениями."""

from __future__ import annotations


class IndexerError(Exception):
    """Базовая ошибка индексатора."""

    def __init__(self, message: str, *, details: str = "") -> None:
        self.details = details
        full = message if not details else f"{message} ({details})"
        super().__init__(full)


class ProfileNotFoundError(IndexerError):
    """Профиль не найден в profiles/."""


class SourceNotFoundError(IndexerError):
    """Каталог исходников проекта недоступен."""


class IndexJobAlreadyRunningError(IndexerError):
    """Для профиля уже выполняется индексация."""


class IndexJobCancelledError(IndexerError):
    """Индексация отменена пользователем."""


class IndexJobNotFoundError(IndexerError):
    """Задача индексации не найдена."""


class IndexEmptyError(IndexerError):
    """Индекс пуст — требуется полная индексация."""


class EmbeddingError(IndexerError):
    """Ошибка построения эмбеддингов."""


class StoreError(IndexerError):
    """Ошибка работы с ChromaDB."""


class GitNotAvailableError(IndexerError):
    """Git недоступен или каталог не является репозиторием."""


class WatchError(IndexerError):
    """Ошибка файлового наблюдателя."""


class ArchiveError(IndexerError):
    """Ошибка экспорта/импорта архива индекса."""


class CompareError(IndexerError):
    """Ошибка сравнения профилей."""


class WizardError(IndexerError):
    """Ошибка мастера настройки."""


class ConfigValidationError(IndexerError):
    """Некорректные параметры конфигурации."""
