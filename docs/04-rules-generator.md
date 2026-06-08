# Генерация файла правил

Раздел **§4** веб-приложения 1C:Cursor: `/rules/`

## Назначение

Чтение проекта 1С (**XML-выгрузка** или **EDT**), анализ метаданных и генерация **markdown-регламента** для AI в Cursor. Конфигурацию 1С не изменяет. **Не** является MCP-сервером.

## Выходные файлы

| Файл | Содержание |
|------|------------|
| `1С-правила-разработки[-ИмяКонфы].md` | Основной регламент |
| `…-журнал-регистрации.md` | Правила записи в журнал регистрации |

По умолчанию (тумблер включён) файлы записываются в:

```
{проект}/.cursor/rules/
```

## Workflow (6 блоков)

1. **Проект** — путь, автоопределение типа (EDT / Конфигуратор), для EDT — подсказки Git.
2. **Анализ** — отчёт `analyze_export()`.
3. **Основные параметры** — поля формы + modal «Дополнительные правила».
4. **Доп. правила** — modal; `create_metadata`: первое открытие **«нет»**, «Рекомендуемые» — **«с разрешения»**.
5. **MCP** — toggles по `mcp.json` (SearXNG, Syntax, KB-профили).
6. **Генерация** — оба `.md`, предпросмотр.

Следующий блок доступен после «зелёного» предыдущего.

## Типы проекта

| Тип | Критерий |
|-----|----------|
| EDT | `.project` + `src/` + ≥1 `*.mdo`, нет `Configuration.xml` в корне |
| XML | `Configuration.xml` в корне |

## API (`/rules/api/`)

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/schema` | Схема формы |
| GET | `/status` | Статус раздела, last_output |
| GET | `/mcp-defaults` | Toggles MCP из mcp.json |
| POST | `/detect-project` | Быстрое определение типа |
| POST | `/analyze` | Анализ проекта |
| POST | `/generate` | Генерация файлов |
| POST | `/pick-directory` | Native folder picker |
| POST | `/pick-save-file` | Native save dialog |
| GET | `/git-hints?path=` | Ветка/remote для EDT |
| POST | `/validate-fields` | Проверка блока «Основные параметры» (workflow UI) |

## Статус раздела

**Готово** на dashboard, когда оба `.md` существуют по путям из `data/settings.json` → `rules.last_output`.

## Troubleshooting

| Симптом | Действие |
|---------|----------|
| «Неверный путь» | Убедитесь в `Configuration.xml` (XML) или `.project`+`src/` (EDT) |
| 409 при генерации | Подтвердите modal «Не обрамлять» (`confirm_unsafe_wrap`) |
| MCP не в правилах | Нажмите «Принять настройки MCP» в блоке §5 |
| Блок заблокирован | Завершите предыдущий workflow-step (зелёный badge) |

## Связь с KB

На странице профиля KB: ссылка «Сгенерировать правила» → `/rules/?project_path=…`

## Пакет Python

Логика в `packages/rules/` (`analyze_export`, `generate_rules_bundle`). Публичный API для тестов и CI, не отдельный CLI.

## См. также

- [05-cursor-mcp-setup.md](05-cursor-mcp-setup.md) — merge mcp.json
- ТЗ §12
