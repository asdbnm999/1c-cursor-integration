"""Анализ иерархической XML-выгрузки конфигурации 1С из конфигуратора."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

# Папки верхнего уровня иерархической выгрузки конфигуратора → тип метаданных
FOLDER_TO_METADATA_RU: dict[str, str] = {
    "AccumulationRegisters": "Регистры накопления",
    "BusinessProcesses": "Бизнес-процессы",
    "Catalogs": "Справочники",
    "ChartsOfAccounts": "Планы счетов",
    "ChartsOfCalculationTypes": "Планы видов расчёта",
    "ChartsOfCharacteristicTypes": "Планы видов характеристик",
    "CommandGroups": "Группы команд",
    "CommonAttributes": "Общие реквизиты",
    "CommonCommands": "Общие команды",
    "CommonForms": "Общие формы",
    "CommonModules": "Общие модули",
    "CommonPictures": "Общие картинки",
    "CommonTemplates": "Общие макеты",
    "Constants": "Константы",
    "DataProcessors": "Обработки",
    "DefinedTypes": "Определяемые типы",
    "DocumentJournals": "Журналы документов",
    "DocumentNumerators": "Нумераторы документов",
    "Documents": "Документы",
    "Enums": "Перечисления",
    "EventSubscriptions": "Подписки на события",
    "ExchangePlans": "Планы обмена",
    "FilterCriteria": "Критерии отбора",
    "FunctionalOptions": "Функциональные опции",
    "FunctionalOptionsParameters": "Параметры функциональных опций",
    "HTTPServices": "HTTP-сервисы",
    "InformationRegisters": "Регистры сведений",
    "IntegrationServices": "Сервисы интеграции",
    "Languages": "Языки",
    "Reports": "Отчёты",
    "Roles": "Роли",
    "ScheduledJobs": "Регламентные задания",
    "SessionParameters": "Параметры сеанса",
    "SettingsStorages": "Хранилища настроек",
    "StyleItems": "Элементы стиля",
    "Styles": "Стили",
    "Subsystems": "Подсистемы",
    "Tasks": "Задачи",
    "WebServices": "Web-сервисы",
    "WSReferences": "WS-ссылки",
    "XDTOPackages": "Пакеты XDTO",
}

NS = {
    "md": "http://v8.1c.ru/8.3/MDClasses",
    "v8": "http://v8.1c.ru/8.1/data/core",
    "dump": "http://v8.1c.ru/8.3/xcf/dumpinfo",
}


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _find_text(parent: ET.Element | None, tag: str) -> str | None:
    if parent is None:
        return None
    for child in parent:
        if _local_tag(child.tag) == tag:
            text = (child.text or "").strip()
            return text or None
    return None


def _find_synonym_ru(properties: ET.Element | None) -> str | None:
    if properties is None:
        return None
    for child in properties:
        if _local_tag(child.tag) != "Synonym":
            continue
        for item in child:
            if _local_tag(item.tag) != "item":
                continue
            lang = None
            content = None
            for sub in item:
                lt = _local_tag(sub.tag)
                if lt == "lang":
                    lang = (sub.text or "").strip()
                elif lt == "content":
                    content = (sub.text or "").strip()
            if lang == "ru" and content:
                return content
    return None


def _version_mode_to_platform(mode: str | None) -> str | None:
    if not mode:
        return None
    m = re.match(r"Version8_3_(\d+)(?:_(\d+))?", mode)
    if m:
        minor = m.group(2)
        return f"8.3.{m.group(1)}" + (f".{minor}" if minor else "")
    return mode.replace("Version", "").replace("_", ".")


@dataclass
class ExportAnalysis:
    """Результат разбора выгрузки."""

    export_path: Path
    is_valid_export: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    config_name: str | None = None
    config_synonym: str | None = None
    config_version: str | None = None
    config_vendor: str | None = None
    config_comment: str | None = None
    name_prefix: str | None = None
    script_variant: str | None = None
    compatibility_mode: str | None = None
    extension_compatibility_mode: str | None = None
    default_run_mode: str | None = None

    dump_format: str | None = None
    dump_version: str | None = None
    export_format_label: str | None = None

    xml_encoding: str | None = None
    bsl_module_count: int = 0
    bsl_uses_regions: bool | None = None
    bsl_indent_tabs: bool | None = None

    metadata_counts: dict[str, int] = field(default_factory=dict)
    metadata_objects: dict[str, list[str]] = field(default_factory=dict)

    project_type: str | None = None  # edt | xml | invalid

    @property
    def project_type_label(self) -> str | None:
        if self.project_type == "edt":
            return "EDT"
        if self.project_type == "xml":
            return "Конфигуратор"
        return None

    @property
    def display_config_name(self) -> str:
        if self.config_synonym and self.config_name:
            return f"{self.config_synonym} ({self.config_name})"
        return self.config_synonym or self.config_name or "—"

    @property
    def platform_hint(self) -> str | None:
        return _version_mode_to_platform(
            self.extension_compatibility_mode or self.compatibility_mode
        )


def _detect_encoding(export_path: Path) -> str | None:
    samples = [
        export_path / "Configuration.xml",
        export_path / "ConfigDumpInfo.xml",
    ]
    for p in samples:
        if not p.is_file():
            continue
        raw = p.read_bytes()[:4]
        if raw.startswith(b"\xef\xbb\xbf"):
            return "UTF-8-BOM"
        if raw.startswith(b"<?xml"):
            return "UTF-8"
    for bsl in export_path.rglob("*.bsl"):
        raw = bsl.read_bytes()[:4]
        if raw.startswith(b"\xef\xbb\xbf"):
            return "UTF-8-BOM"
        return "UTF-8"
    return None


def _analyze_bsl(export_path: Path) -> tuple[int, bool | None, bool | None]:
    modules = list(export_path.rglob("*.bsl"))
    if not modules:
        return 0, None, None
    uses_regions = False
    tab_indents = 0
    space_indents = 0
    for path in modules[:20]:
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="cp1251")
            except UnicodeDecodeError:
                continue
        if "#Область" in text or "#Region" in text:
            uses_regions = True
        for line in text.splitlines()[:80]:
            if not line.strip():
                continue
            if line.startswith("\t"):
                tab_indents += 1
            elif line.startswith("    "):
                space_indents += 1
            break
    indent_tabs: bool | None = None
    if tab_indents or space_indents:
        indent_tabs = tab_indents >= space_indents
    return len(modules), uses_regions, indent_tabs


def _count_metadata(export_path: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    counts: dict[str, int] = {}
    objects: dict[str, list[str]] = {}
    for folder_name, label in FOLDER_TO_METADATA_RU.items():
        folder = export_path / folder_name
        if not folder.is_dir():
            continue
        names: list[str] = []
        for xml_file in sorted(folder.glob("*.xml")):
            names.append(xml_file.stem)
        if names:
            counts[label] = len(names)
            objects[label] = names
    return counts, objects


def _parse_configuration(export_path: Path) -> dict[str, str | None]:
    cfg_path = export_path / "Configuration.xml"
    result: dict[str, str | None] = {
        "config_name": None,
        "config_synonym": None,
        "config_version": None,
        "config_vendor": None,
        "config_comment": None,
        "name_prefix": None,
        "script_variant": None,
        "compatibility_mode": None,
        "extension_compatibility_mode": None,
        "default_run_mode": None,
    }
    if not cfg_path.is_file():
        return result
    tree = ET.parse(cfg_path)
    root = tree.getroot()
    config_el = None
    for child in root:
        if _local_tag(child.tag) == "Configuration":
            config_el = child
            break
    if config_el is None:
        return result
    props = None
    for child in config_el:
        if _local_tag(child.tag) == "Properties":
            props = child
            break
    if props is None:
        return result
    result["config_name"] = _find_text(props, "Name")
    result["config_synonym"] = _find_synonym_ru(props)
    result["config_version"] = _find_text(props, "Version")
    result["config_vendor"] = _find_text(props, "Vendor")
    result["config_comment"] = _find_text(props, "Comment")
    prefix = _find_text(props, "NamePrefix")
    result["name_prefix"] = prefix if prefix else None
    result["script_variant"] = _find_text(props, "ScriptVariant")
    result["compatibility_mode"] = _find_text(props, "CompatibilityMode")
    result["extension_compatibility_mode"] = _find_text(
        props, "ConfigurationExtensionCompatibilityMode"
    )
    result["default_run_mode"] = _find_text(props, "DefaultRunMode")
    return result


def _parse_dump_info(export_path: Path) -> dict[str, str | None]:
    info_path = export_path / "ConfigDumpInfo.xml"
    result = {"dump_format": None, "dump_version": None, "export_format_label": None}
    if not info_path.is_file():
        return result
    tree = ET.parse(info_path)
    root = tree.getroot()
    result["dump_format"] = root.attrib.get("format")
    result["dump_version"] = root.attrib.get("version")
    fmt = result["dump_format"]
    if fmt == "Hierarchical":
        result["export_format_label"] = "Конфигуратор (иерархическая выгрузка)"
    elif fmt:
        result["export_format_label"] = f"Выгрузка (format={fmt})"
    return result


def _count_mdo_files(path: Path) -> int:
    return len(list(path.rglob("*.mdo")))


def _detect_project_type(path: Path) -> tuple[str, list[str]]:
    """ТЗ §12.5: EDT | XML | invalid."""
    has_cfg_root = (path / "Configuration.xml").is_file()
    has_project = (path / ".project").is_file()
    has_src = (path / "src").is_dir()
    mdo_count = _count_mdo_files(path) if has_src else 0
    signs: list[str] = []

    if has_project:
        signs.append(".project")
    if has_src:
        signs.append("src/")
    if mdo_count:
        signs.append(f"*.mdo ({mdo_count})")
    if has_cfg_root:
        signs.append("Configuration.xml (корень)")

    if has_project and has_src and mdo_count >= 1 and not has_cfg_root:
        return "edt", signs
    if has_cfg_root:
        return "xml", signs
    if has_project or has_src or mdo_count:
        return "invalid", signs
    return "invalid", signs


def _find_configuration_mdo(path: Path) -> Path | None:
    preferred = path / "src" / "Configuration" / "Configuration.mdo"
    if preferred.is_file():
        return preferred
    for candidate in path.rglob("Configuration.mdo"):
        if candidate.is_file():
            return candidate
    return None


def _parse_edt_configuration(path: Path) -> dict[str, str | None]:
    result: dict[str, str | None] = {
        "config_name": None,
        "config_synonym": None,
        "config_version": None,
        "config_vendor": None,
        "config_comment": None,
        "name_prefix": None,
        "script_variant": None,
        "compatibility_mode": None,
        "extension_compatibility_mode": None,
        "default_run_mode": None,
    }
    mdo_path = _find_configuration_mdo(path)
    if not mdo_path:
        return result
    try:
        tree = ET.parse(mdo_path)
        root = tree.getroot()
    except ET.ParseError:
        return result

    result["config_name"] = _find_text(root, "name")
    for child in root:
        if _local_tag(child.tag) != "synonym":
            continue
        lang = None
        value = None
        for sub in child:
            lt = _local_tag(sub.tag)
            if lt == "key":
                lang = (sub.text or "").strip()
            elif lt == "value":
                value = (sub.text or "").strip()
        if lang == "ru" and value:
            result["config_synonym"] = value
            break

    result["config_version"] = _find_text(root, "version")
    result["script_variant"] = _find_text(root, "scriptVariant")
    result["compatibility_mode"] = _find_text(root, "compatibilityMode")
    result["extension_compatibility_mode"] = _find_text(
        root, "configurationExtensionCompatibilityMode"
    )
    result["default_run_mode"] = _find_text(root, "defaultRunMode")
    return result


def _count_edt_metadata(path: Path) -> tuple[dict[str, int], dict[str, list[str]]]:
    counts: dict[str, int] = {}
    objects: dict[str, list[str]] = {}
    src = path / "src"
    if not src.is_dir():
        return counts, objects
    for folder_name, label in FOLDER_TO_METADATA_RU.items():
        folder = src / folder_name
        if not folder.is_dir():
            continue
        names: list[str] = []
        for child in sorted(folder.iterdir()):
            if not child.is_dir():
                continue
            mdo = child / f"{child.name}.mdo"
            if mdo.is_file():
                names.append(child.name)
        if names:
            counts[label] = len(names)
            objects[label] = names
    return counts, objects


def _analyze_xml_export(path: Path, analysis: ExportAnalysis) -> ExportAnalysis:
    has_cfg = (path / "Configuration.xml").is_file()
    has_dump = (path / "ConfigDumpInfo.xml").is_file()
    if not has_cfg:
        analysis.errors.append("Не найден Configuration.xml в корне выгрузки.")
    if not has_dump:
        analysis.warnings.append("Не найден ConfigDumpInfo.xml — часть сведений недоступна.")

    analysis.is_valid_export = has_cfg
    analysis.project_type = "xml"

    cfg = _parse_configuration(path)
    for key, value in cfg.items():
        setattr(analysis, key, value)

    dump = _parse_dump_info(path)
    analysis.dump_format = dump["dump_format"]
    analysis.dump_version = dump["dump_version"]
    analysis.export_format_label = dump["export_format_label"] or "Конфигуратор (иерархическая выгрузка)"

    analysis.xml_encoding = _detect_encoding(path)
    bsl_count, regions, tabs = _analyze_bsl(path)
    analysis.bsl_module_count = bsl_count
    analysis.bsl_uses_regions = regions
    analysis.bsl_indent_tabs = tabs

    counts, objects = _count_metadata(path)
    analysis.metadata_counts = counts
    analysis.metadata_objects = objects
    return analysis


def _analyze_edt_export(path: Path, analysis: ExportAnalysis) -> ExportAnalysis:
    analysis.is_valid_export = True
    analysis.project_type = "edt"
    analysis.export_format_label = "Проект EDT"

    cfg = _parse_edt_configuration(path)
    for key, value in cfg.items():
        setattr(analysis, key, value)

    if not cfg.get("config_name"):
        analysis.warnings.append("Не найден или не разобран Configuration.mdo в проекте EDT.")

    src = path / "src"
    bsl_count, regions, tabs = _analyze_bsl(src if src.is_dir() else path)
    analysis.bsl_module_count = bsl_count
    analysis.bsl_uses_regions = regions
    analysis.bsl_indent_tabs = tabs
    analysis.xml_encoding = _detect_encoding(src if src.is_dir() else path)

    counts, objects = _count_edt_metadata(path)
    analysis.metadata_counts = counts
    analysis.metadata_objects = objects
    return analysis


def analyze_export(export_path: str | Path) -> ExportAnalysis:
    path = Path(export_path).expanduser().resolve()
    analysis = ExportAnalysis(export_path=path, is_valid_export=False)

    if not path.is_dir():
        analysis.errors.append(f"Путь не существует или не является каталогом: {path}")
        return analysis

    project_type, signs = _detect_project_type(path)
    analysis.project_type = project_type

    if project_type == "edt":
        return _analyze_edt_export(path, analysis)
    if project_type == "xml":
        return _analyze_xml_export(path, analysis)

    analysis.errors.append(
        "Проект не распознан: нужен EDT (.project + src/ + ≥1 *.mdo, без Configuration.xml в корне) "
        "или XML-выгрузка (Configuration.xml в корне)."
    )
    if signs:
        analysis.errors.append(f"Обнаружено: {', '.join(signs)}")
    return analysis
