"""Соответствие папок метаданных и типов объектов 1С."""

FOLDER_TO_OBJECT_TYPE: dict[str, str] = {
    "Configuration": "Configuration",
    "Subsystems": "Subsystem",
    "Documents": "Document",
    "Catalogs": "Catalog",
    "InformationRegisters": "InformationRegister",
    "AccumulationRegisters": "AccumulationRegister",
    "AccountingRegisters": "AccountingRegister",
    "Reports": "Report",
    "DataProcessors": "DataProcessor",
    "CommonModules": "CommonModule",
    "EventSubscriptions": "EventSubscription",
    "ScheduledJobs": "ScheduledJob",
    "HTTPServices": "HTTPService",
    "WebServices": "WebService",
    "Enums": "Enum",
    "ChartsOfAccounts": "ChartOfAccounts",
    "ChartsOfCalculationTypes": "ChartOfCalculationTypes",
    "ChartsOfCharacteristicTypes": "ChartOfCharacteristicTypes",
    "BusinessProcesses": "BusinessProcess",
    "Tasks": "Task",
    "ExchangePlans": "ExchangePlan",
    "Roles": "Role",
    "CommonCommands": "CommonCommand",
    "CommonForms": "CommonForm",
    "CommonAttributes": "CommonAttribute",
    "DefinedTypes": "DefinedType",
    "FunctionalOptions": "FunctionalOption",
    "Constants": "Constant",
    "DocumentJournals": "DocumentJournal",
    "Sequences": "Sequence",
    "FilterCriteria": "FilterCriterion",
    "XDTOPackages": "XDTOPackage",
    "WebSocketClients": "WebSocketClient",
    "IntegrationServices": "IntegrationService",
}

XML_ROOT_TO_OBJECT_TYPE: dict[str, str] = {
    "Configuration": "Configuration",
    "Subsystem": "Subsystem",
    "Document": "Document",
    "Catalog": "Catalog",
    "InformationRegister": "InformationRegister",
    "AccumulationRegister": "AccumulationRegister",
    "AccountingRegister": "AccountingRegister",
    "Report": "Report",
    "DataProcessor": "DataProcessor",
    "CommonModule": "CommonModule",
    "EventSubscription": "EventSubscription",
    "ScheduledJob": "ScheduledJob",
    "HTTPService": "HTTPService",
    "WebService": "WebService",
    "Enum": "Enum",
    "ChartOfAccounts": "ChartOfAccounts",
    "ChartOfCalculationTypes": "ChartOfCalculationTypes",
    "ChartOfCharacteristicTypes": "ChartOfCharacteristicTypes",
    "BusinessProcess": "BusinessProcess",
    "Task": "Task",
    "ExchangePlan": "ExchangePlan",
    "Role": "Role",
    "CommonCommand": "CommonCommand",
    "Constant": "Constant",
}

INDEXABLE_SUFFIXES = frozenset({".bsl", ".mdo", ".xml", ".md"})

BSL_MODULE_NAMES = {
    "Module.bsl",
    "ObjectModule.bsl",
    "ManagerModule.bsl",
    "RecordSetModule.bsl",
    "CommandModule.bsl",
    "FormModule.bsl",
}

FORM_XML_SKIP_NAMES = frozenset({
    "Help.xml",
    "Picture.xml",
    "Predefined.xml",
})

# Полная индексация конфигурации: все типы метаданных с кодом/структурой
DEFAULT_EDT_INCLUDE_DIRS: list[str] = [
    "Configuration",
    "Subsystems",
    "Documents",
    "Catalogs",
    "InformationRegisters",
    "AccumulationRegisters",
    "AccountingRegisters",
    "Reports",
    "DataProcessors",
    "CommonModules",
    "EventSubscriptions",
    "ScheduledJobs",
    "HTTPServices",
    "WebServices",
    "Enums",
    "BusinessProcesses",
    "Tasks",
    "ExchangePlans",
    "Roles",
    "CommonCommands",
    "CommonForms",
    "Constants",
    "DocumentJournals",
    "ChartsOfAccounts",
    "ChartsOfCalculationTypes",
    "ChartsOfCharacteristicTypes",
    "DefinedTypes",
    "FunctionalOptions",
    "FilterCriteria",
    "Sequences",
]

DEFAULT_XML_INCLUDE_DIRS: list[str] = list(FOLDER_TO_OBJECT_TYPE.keys())

# Только визуальный/служебный шум — без БСП и бизнес-логики
DEFAULT_EXCLUDE_DIRS: list[str] = [
    "StyleItems",
    "CommonPictures",
    "CommonTemplates",
    "Languages",
    "SessionParameters",
    "SettingsStorages",
    "CommandGroups",
    "CommonTemplates",
]

DEFAULT_EDT_EXCLUDE_GLOBS: list[str] = [
    "**/Templates/**",
    "**/*.png",
    "**/*.gif",
    "**/*.bmp",
    "**/*.bin",
    "**/.DS_Store",
    "**/.settings/**",
    "**/DT-INF/**",
]

DEFAULT_XML_EXCLUDE_GLOBS: list[str] = [
    "**/Forms/**/*.xml",  # см. include_forms в config
    "**/Ext/*.xml",
    "**/Predefined.xml",
    "**/Help.xml",
    "**/Picture.xml",
    "**/ConfigDumpInfo.xml",
    "**/*.png",
    "**/.DS_Store",
]
