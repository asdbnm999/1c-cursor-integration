# Документация 1C:Cursor

**Версия проекта:** 1.0.0  
**Язык:** русский  
**Источник истины:** `1C-Cursor-ТЗ.md` v1.4

---

## С чего начать

| Вы | Начните с |
|----|-----------|
| Пользователь Cursor + 1С | **[Визуальный быстрый старт](quick-start.md)** → [корневой README](../README.md) |
| Настройка MCP | [02-mcp-docker](02-mcp-docker.md) → [05-cursor-mcp-setup](05-cursor-mcp-setup.md) |
| Индексация конфигурации | [03-knowledge-base](03-knowledge-base.md) |
| Правила для AI | [04-rules-generator](04-rules-generator.md) |
| Разработчик / AI-агент | [AGENT_HANDOFF](AGENT_HANDOFF.md) |

Встроенная справка в UI: иконка **?** на dashboard и ссылки **«Подробнее»** → `/docs/<файл>.md`.

---

## Пользовательская документация

| Файл | Раздел | Содержание |
|------|--------|------------|
| [quick-start.md](quick-start.md) | Все § | Визуальная пошаговая настройка со скриншотами |
| [01-plugins.md](01-plugins.md) | §1 VS-плагины | VSIX, каталоги Cursor, конфликт версий, API |
| [02-mcp-docker.md](02-mcp-docker.md) | §2 MCP Docker | SearXNG, Syntax, HBK, порты 82xx, ресурсы, deploy |
| [03-knowledge-base.md](03-knowledge-base.md) | §3 KB | Профили, индексация, watch, MCP tools, 83xx |
| [04-rules-generator.md](04-rules-generator.md) | §4 Правила | Workflow, EDT/XML, MCP в правилах, `.cursor/rules` |
| [05-cursor-mcp-setup.md](05-cursor-mcp-setup.md) | MCP общее | `mcp.json`, merge, бэкапы, Refresh, multi-KB |
| [errors/mcp-docker.json](errors/mcp-docker.json) | §2 UI | Каталог типовых ошибок Docker (modal «Типовые ошибки») |

---

## Для разработчиков и AI-агентов

| Файл | Аудитория | Содержание |
|------|-----------|------------|
| [AGENT_HANDOFF.md](AGENT_HANDOFF.md) | AI / разработчик | Архитектура, API map, статусы, conventions |
| [kb/AGENT_HANDOFF.md](kb/AGENT_HANDOFF.md) | AI / KB | Детали vendored KB (исторический handoff) |
| [kb/ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md](kb/ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md) | Пользователь KB | Расширенные сценарии KB |
| [kb/DEPLOYMENT_TLS.md](kb/DEPLOYMENT_TLS.md) | Администратор | nginx/Caddy, TLS (опционально) |
| [kb/EDT_FORMS_AUDIT.md](kb/EDT_FORMS_AUDIT.md) | Разработчик | `include_forms`, переиндексация |

---

## Карта разделов приложения

```
http://127.0.0.1:8080/
├── /                 Dashboard: статусы, диагностика, wizard, export/import
├── /plugins/         §1
├── /mcp/             §2
├── /kb/              §3 список профилей
├── /kb/profile/<n>   §3 профиль (index → docker → mcp)
├── /rules/           §4
└── /docs/<file>      Отдача markdown из docs/
```

---

## API (краткая карта)

| Префикс | Документ |
|---------|----------|
| `/api/` | [AGENT_HANDOFF §4](AGENT_HANDOFF.md#4-маршруты-веб-сервера) — dashboard, system, settings, sections, mcp |
| `/plugins/api/` | [01-plugins § API](01-plugins.md#api) |
| `/mcp/api/` | [02-mcp-docker § API](02-mcp-docker.md#api) |
| `/kb/api/` | [03-knowledge-base](03-knowledge-base.md), [AGENT_HANDOFF](AGENT_HANDOFF.md) |
| `/rules/api/` | [04-rules-generator § API](04-rules-generator.md#api-rulesapi) |

---

## Тестирование и CI

```bash
pip install -e ".[kb,dev]"
pytest -q                    # 259 passed
./scripts/run_tests.sh
```

GitHub Actions: `.github/workflows/tests.yml` (Python 3.11, 3.12, 3.13).

---

## Правила сопровождения документации

1. **Изменение API** — обновить `AGENT_HANDOFF.md` и соответствующий user doc (`01`–`05`).
2. **Новая типовая ошибка Docker** — запись в `errors/mcp-docker.json` + проверка modal в §2.
3. **User docs** — русский язык, пошагово; не дублировать ТЗ целиком.
4. **Релиз** — запись в [CHANGELOG.md](../CHANGELOG.md), версия в `pyproject.toml` и README.

---

## Внешние источники (при разработке)

| Материал | Использование |
|----------|---------------|
| `1C-Cursor-ТЗ.md` | Требования v1.4 |
| `1C-Cursor-план-разработки.md` | План шагов 0–9 |
| `MCP-Docker-сборка-и-фиксы.md` | Приоритет для Docker §2 |
| `MCP-Docker-SearXNG-и-1C-Syntax-гайд.md` | Шаблоны compose |

---

*Документация §22 финализирована (шаг 9). Все файлы карты ТЗ созданы и синхронизированы с кодом v1.0.0.*
