from __future__ import annotations

import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_PROFILES = PROJECT_ROOT / "data" / "profiles"

# Каталоги data/profiles/*, которые создают тесты (не пользовательские профили).
TEST_DATA_PROFILE_DIRS = frozenset({
    "api-int-clone",
    "api-int-temp",
    "edt-forms-meta",
    "edt-forms-off",
    "edt-forms-on",
    "forms-off-test",
    "forms-on-test",
    "imported-fixture",
    "test-fixture",
    "test-fixture-bsl-a",
    "test-fixture-bsl-b",
    "test-fixture-clone",
    "test-fixture-copy-idx",
    "recreate-test",
})


def _cleanup_test_data_profiles() -> None:
    for name in TEST_DATA_PROFILE_DIRS:
        for base in (DATA_PROFILES, PROJECT_ROOT / "profiles"):
            path = base / name
            if path.exists():
                shutil.rmtree(path, ignore_errors=True)


@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data_profiles_after_session():
    yield
    _cleanup_test_data_profiles()


@pytest.fixture
def xml_export_tree(tmp_path: Path) -> Path:
    docs = tmp_path / "Documents"
    docs.mkdir()
    shutil.copy(FIXTURES / "xml_document.xml", docs / "ТестовыйДокумент.xml")
    bsl_dir = docs / "ТестовыйДокумент" / "Ext"
    bsl_dir.mkdir(parents=True)
    (bsl_dir / "ObjectModule.bsl").write_text(
        """Процедура ОбработкаПроведения(Отказ, Режим)
    Движение = Движения.ТестовыйРегистр.Добавить();
    Движение.ВидДвижения = ВидДвиженияНакопления.Расход;
КонецПроцедуры

Процедура Проведение() Экспорт
КонецПроцедуры
""",
        encoding="utf-8",
    )
    return tmp_path


@pytest.fixture
def fixture_profile_config(tmp_path: Path, xml_export_tree: Path) -> Path:
    profiles_dir = PROJECT_ROOT / "profiles" / "test-fixture"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    content = (FIXTURES / "profile_config.yaml").read_text(encoding="utf-8")
    content = content.replace("FIXTURE_ROOT", str(xml_export_tree))
    config_path = profiles_dir / "config.yaml"
    config_path.write_text(content, encoding="utf-8")
    yield config_path
    if config_path.exists():
        config_path.unlink()
    if profiles_dir.exists() and not any(profiles_dir.iterdir()):
        profiles_dir.rmdir()
