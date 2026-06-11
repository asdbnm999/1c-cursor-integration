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
5. **MCP** — toggles по `mcp.json` (SearXNG, Syntax, KB-профили). При включённом KB-профиле в правила попадает таблица **5 tools** MCP (`search_project`, `get_object`, `list_by_relation`, `get_module`, `find_references`), параметры и матрица «вопрос → tool»; при нескольких профилях — напоминание спросить базу в начале диалога.
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

## Пример блока MCP (KB включена)

Фрагмент из `packages/rules/mcp_rules.py` → `build_mcp_rules_section()`:

```markdown
- **База знаний проекта:** использовать MCP `1c-kb-myconf` для работы с метаданными и кодом **этой** конфигурации. Не парсить XML/BSL вручную, если ответ можно получить через tools ниже.

  **Инструменты MCP `1c-kb-myconf` (5 методов):**

  | Tool | Когда вызывать |
  |------|----------------|
  | `search_project` | Не знаешь точное имя объекта; поиск по смыслу по всей конфигурации |
  | `get_object` | Карточка объекта: структура, движения, проведение |
  ...

  **Матрица «вопрос → tool»:** …
```

Полная спецификация tools — `docs/kb/AGENT_HANDOFF.md` §7.

## См. также

- [05-cursor-mcp-setup.md](05-cursor-mcp-setup.md) — merge mcp.json
- [kb/AGENT_HANDOFF.md](kb/AGENT_HANDOFF.md) §7 — API KB MCP
- ТЗ §12
