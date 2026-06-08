# Changelog

## 1.0.0 — 2026-06-07

Первый релиз **1C:Cursor** — все шаги плана разработки (0–9) завершены.

### Documentation (шаг 9 — §22)

- `README.md` — полный quick start, 4 раздела, CLI, тесты, Attributions, порты
- `docs/README.md` — оглавление, карта API, правила сопровождения docs
- Синхронизированы user docs `01`–`05` с финальным кодом (dashboard, workflow, troubleshooting)
- `docs/AGENT_HANDOFF.md` — v1.0.0, тесты 226 passed, CI, карта §22 ✅

### Release summary

| Компонент | Статус |
|-----------|--------|
| §1 Plugins | VSIX install, API, conflict modal |
| §2 MCP Docker | SearXNG + Syntax, 82xx, compose generator |
| §3 KB | Профили, индексация, 83xx, 8 MCP tools |
| §4 Rules | EDT/XML, workflow, `.cursor/rules` |
| Dashboard | 4 карточки, wizard, RAM, export/import |
| Tests | **226 passed** (122 KB) |
| CI | GitHub Actions Python 3.11–3.13 |

## 0.9.0 — 2026-06-07

### Added (шаг 8 — тестирование)

- `tests/conftest.py` — общие пути фикстур XML/EDT, pytest markers
- `tests/test_mcp_section.py` — статус §2, конфликты портов 82xx
- `tests/test_kb_ports.py` — порты 83xx, naming `-mcp`, `allocate_http_port`
- `tests/test_sections_status.py` — интеграция статусов §6.4
- `tests/test_acceptance_tz15.py` — мета-пороги ТЗ §15 (122+ KB tests)
- `.github/workflows/tests.yml` — CI pytest на Python 3.11–3.13
- `scripts/run_tests.sh` — локальный прогон

### Changed

- Расширены: `test_cursor_mcp.py`, `test_system_check.py`, `test_plugins.py`, `test_rules_api.py`
- `tests/kb/test_docker_compose.py` — порты **8301+** вместо 8010+
- `pyproject.toml` — pytest markers, `addopts`

### Tests

- **226 passed** (122 KB + 104 остальных)

## 0.8.0 — 2026-06-07

### Added (шаг 7 — интеграция dashboard)

- `web/sections.py` — единый пересчёт статусов §1–§4, snapshot для карточек и wizard
- Dashboard: 4 карточки (§2 MCP), описания, wizard с бейджами, RAM estimate, export/import JSON
- API `/api/sections/status`, `/api/sections/refresh`, маршрут `/docs/<file>`
- `docs/AGENT_HANDOFF.md` — полная архитектурная документация
- `tests/test_integration_dashboard.py` (+8 тестов)

### Changed

- `web/routes/__init__.py` — dashboard через `build_sections_snapshot()`
- `web/system_check.py` — `estimate_mcp_ram_mb()` в `/api/system`
- `web/kb/service.py` — `update_kb_section_status_in_settings()`
- `web/rules/service.py` — синхронизация computed status в settings

## 0.6.0 — 2026-06-07

### Added (шаг 5 — §3 KB UI/API)

- `web/routes/kb.py` — `/kb/`, `/kb/profile/<name>`, API `/kb/api/*` (полный перенос project-kb-mcp)
- `web/templates/kb/`, `web/static/js/kb.js`, `web/static/css/kb.css`
- `web/kb/service.py` — статус раздела для dashboard
- `docs/03-knowledge-base.md` — пользовательская документация
- `tests/test_kb_api.py`; включены 6 отложенных `tests/kb/test_api_*.py`
- Порты профилей KB: **8301+** (profiles, config, template)

### Changed

- `packages/kb/indexer/api_auth.py` — scope `/kb/api/` (не блокирует dashboard)
- `web/app.py` — register KB, restore watchers, `app` для тестов

## 0.5.0 — 2026-06-07

### Added (шаг 4 — §2 MCP Docker)

- `web/mcp_compose.py` — генерация compose SearXNG и 1C Syntax (порты 82xx, naming `{slug}-mcp`)
- `web/mcp/` — constants, deploy, service, syntax_patch, errors_catalog
- `web/routes/mcp.py` — UI `/mcp/` и API `/mcp/api/*`
- `web/templates/mcp/index.html`, `web/static/js/mcp.js`
- `docs/02-mcp-docker.md`, `docs/05-cursor-mcp-setup.md`, `docs/errors/mcp-docker.json`
- `docker_templates/searxng/`, `docker_templates/1c-syntax/` — README шаблонов
- `web/plugins/native_dialogs.py` — `pick_file()` для HBK
- Тесты: `tests/test_mcp_compose.py`, `tests/test_mcp_api.py`

## 0.4.0 — 2026-06-07

### Added (шаги 2A + 2B — vendoring KB и Rules)

- `packages/kb/` — indexer, mcp_server, docker из project-kb-mcp
- `packages/rules/` — парсер правил (без tkinter, choice_field, ui_theme, vendor/flask)
- `packages/kb/paths.py` — PROJECT_ROOT monorepo
- `tests/kb/` — 85 тестов (6 API-тестов отложены до шага 5)
- `scripts/kb/`, `deploy/kb/`, `docs/kb/`
- `[project.optional-dependencies] kb` — chromadb, sentence-transformers, mcp, …
- Адаптация Docker: `packages/kb/docker/Dockerfile`, compose `-mcp`, entrypoint `1c-cursor-kb-mcp`
- `tests/test_rules_import.py`

## 0.3.0 — 2026-06-07

### Added (шаг 3 — §1 Plugins)

- Пакет `web/plugins/` — VSIX metadata, paths, installer, native dialogs, service
- `web/routes/plugins.py` — страница `/plugins/` и API `/plugins/api/*`
- UI: bundled/additional VSIX, каталог Cursor, batch install, conflict modal
- `docs/01-plugins.md` — пользовательская документация
- Тесты `tests/test_plugins.py` (16 тестов)

## 0.2.0 — 2026-06-07

### Added (шаг 1)

- `web/system_check.py` — диагностика Python, Docker, RAM, порты
- `web/routes/dashboard.py` — API `/api/system`, `/api/mcp/*`, export/import settings
- HTTP health-check MCP в `web/cursor_mcp.py` (httpx)
- Dashboard: таблицы диагностики, MCP panel, warnings, Docker badge/banner
- `web/static/js/dashboard.js`
- Тесты: `test_cursor_mcp.py`, `test_system_check.py`

## 0.1.0 — 2026-06-07

### Added (шаг 0)

- Monorepo каркас `1c-cursor`
- Flask web `1c-cursor-web` на `127.0.0.1:8080`
- Dashboard с 4 карточками разделов
- Stub-маршруты `/plugins/`, `/mcp/`, `/kb/`, `/rules/`
- Модули `web/docker_naming.py`, `web/cursor_mcp.py` (каркас)
- 4 тёмные палитры UI
- Bundled VSIX в `assets/extensions/`
- Skeleton документации §22
- Git repository initialized
