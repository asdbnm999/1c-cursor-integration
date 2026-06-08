# AGENT_HANDOFF — 1C:Cursor

> Архитектура monorepo для AI-агентов и разработчиков.  
> Источник истины: `1C-Cursor-ТЗ.md` v1.4. План: `1C-Cursor-план-разработки.md`.

**Версия проекта:** 1.0.0 (релиз документации §22, шаги 0–9 завершены)

---

## 1. Назначение

**1C:Cursor** — единое кроссплатформенное веб-приложение (Flask, `:8080`) для настройки среды разработки конфигураций 1С в Cursor IDE:

| § | Раздел | URL | Пакет |
|---|--------|-----|-------|
| 1 | VS-плагины | `/plugins/` | `web/plugins/` |
| 2 | Стандартные MCP | `/mcp/` | `web/mcp/`, `web/mcp_compose.py` |
| 3 | Векторная KB | `/kb/` | `packages/kb/`, `web/routes/kb.py` |
| 4 | Генерация правил | `/rules/` | `packages/rules/`, `web/routes/rules.py` |

Правила (§4) **не** MCP-сервер и не попадают в `mcp.json`.

---

## 2. Структура monorepo

```
1c-cursor/
├── pyproject.toml              # entry points: 1c-cursor-web, 1c-cursor-kb-index, …
├── data/                       # runtime (.gitignore): settings, profiles data, hf_cache
├── assets/extensions/          # bundled VSIX
├── packages/
│   ├── kb/                     # vendored project-kb-mcp
│   └── rules/                  # vendored ПарсингКонфыДляПравил
├── web/
│   ├── app.py                  # create_app(), blueprints
│   ├── sections.py             # интеграция статусов §1–§4 (шаг 7)
│   ├── cursor_mcp.py           # merge mcp.json, backup TTL 3 дня
│   ├── docker_naming.py        # {slug}-mcp, auxiliary names
│   ├── system_check.py         # Docker, порты, RAM estimate
│   ├── settings.py
│   ├── routes/                 # dashboard, plugins, mcp, kb, rules
│   ├── plugins/, mcp/, kb/, rules/  # бизнес-логика разделов
│   ├── templates/, static/
├── docker_templates/searxng/, 1c-syntax/
├── profiles/_template/
├── tests/                      # unit + kb (122+) + integration
└── docs/                       # §22 user + AGENT_HANDOFF
```

---

## 3. Точки входа

```bash
pip install -e ".[kb,dev]"
1c-cursor-web                    # http://127.0.0.1:8080
1c-cursor-kb-index --profile X --full
1c-cursor-kb-mcp
```

Deprecated: `kb-index`, `kb-mcp` (stderr warning).

---

## 4. Маршруты веб-сервера

### Страницы

| Path | Blueprint |
|------|-----------|
| `/` | `web/routes/__init__.py` (dashboard) |
| `/plugins/` | `web/routes/plugins.py` |
| `/mcp/` | `web/routes/mcp.py` |
| `/kb/`, `/kb/profile/<name>` | `web/routes/kb.py` |
| `/rules/` | `web/routes/rules.py` |
| `/docs/<file>` | `web/routes/dashboard.py` (markdown из `docs/`) |

### API — глобальный (dashboard)

| Method | Path | Модуль |
|--------|------|--------|
| GET | `/api/health` | `web/app.py` |
| GET | `/api/system` | `web/system_check.py` |
| GET/PUT | `/api/settings/ui` | `web/app.py` |
| GET | `/api/settings/export` | `web/settings.py` |
| POST | `/api/settings/import` | `web/settings.py` |
| GET | `/api/sections/status` | `web/sections.py` |
| POST | `/api/sections/refresh` | `web/sections.py` |
| GET | `/api/mcp/status` | `web/cursor_mcp.py` |
| POST | `/api/mcp/check` | `web/cursor_mcp.py` |
| POST | `/api/mcp/preview` | `web/cursor_mcp.py` |

### API — разделы

| Prefix | Файл |
|--------|------|
| `/plugins/api/` | `web/routes/plugins.py` |
| `/mcp/api/` | `web/routes/mcp.py` |
| `/kb/api/` | `web/routes/kb.py` (Bearer `KB_API_TOKEN`) |
| `/rules/api/` | `web/routes/rules.py` |

---

## 5. Интеграция статусов (шаг 7)

**Модуль:** `web/sections.py`

| Функция | Назначение |
|---------|------------|
| `refresh_all_section_statuses()` | Пересчёт + запись в `data/settings.json` → `sections.*` |
| `build_sections_snapshot()` | Карточки dashboard + wizard steps |

### Условия `ready` (ТЗ §6.4)

| Раздел | Вычисление |
|--------|------------|
| §1 plugins | `web/plugins/service.compute_section_status` — оба bundled VSIX |
| §2 mcp | `web/mcp/service.compute_section_status` — оба стандартных MCP: Up + health + mcp.json |
| §3 kb | `web/kb/service.compute_kb_section_status` — ≥1 профиль ready + container + mcp |
| §4 rules | `web/rules/service.compute_rules_section_status` — оба `.md` по `last_output` |

Dashboard при загрузке и `/api/sections/status?refresh=1` вызывают пересчёт.

---

## 6. MCP и Docker

### Именование (§7.2)

```python
from web.docker_naming import mcp_stack_name, auxiliary_name
mcp_stack_name("searxng")  # → searxng-mcp
```

Ключ в `mcp.json` **без** суффикса `-mcp`: `searxng`, `1c-syntax-helper`, `1c-kb-<profile>`.

### Порты

| Зона | Порты |
|------|-------|
| §2 SearXNG MCP / Core / Syntax | 8201, 8202, 8203 |
| §3 KB профиль N | 8300+N (1-й → 8301) |

### `web/cursor_mcp.py`

- `merge_servers()` — не затирает чужие серверы
- `apply_standard_mcp()`, `apply_kb_profile()`
- Бэкапы: `data/cursor-mcp-backups/`, TTL 3 дня
- URL только `127.0.0.1`

### Compose

- Генератор: `web/mcp_compose.py`
- Шаблоны: `docker_templates/`
- Deploy: `web/mcp/deploy.py` (`docker compose up -d`, **не** `compose run`)
- Default docker root: `~/DockerMCP/`

---

## 7. Vendored packages

### `packages/kb/`

Индексация на хосте, MCP в Docker. Адаптировано:

- API prefix `/kb/api/`
- Порты 83xx
- `PROJECT_ROOT` = корень 1c-cursor
- MCP merge через `web/cursor_mcp.py` / `cursor_mcp_config.py`

Ключевые модули: `indexer/`, `mcp_server/`, `docker/`.

### `packages/rules/`

Публичный API (тесты/CI): `analyze_export`, `generate_rules_bundle`.  
UI только через `/rules/`. Удалены tkinter, vendor/flask.

---

## 8. Настройки

| Файл | Содержимое |
|------|------------|
| `data/settings.json` | UI palette, docker root, mcp standard, sections, rules.last_output |
| `data/cursor-settings.json` | cursor_extensions_dir, mcp_config_path |

Экспорт/импорт (без Chroma): `/api/settings/export`, `/api/settings/import`.  
KB archive с индексами: `/kb/api/profiles/<name>/export` (`.tar.gz`).

---

## 9. UI conventions

- **Только тёмная тема** (light удалён)
- Палитры: `midnight`, `ocean`, `forest`, `ember`
- Header: `1C:Cursor` + subtitle по разделу (§6.2)
- Tooltips `?` на dashboard; ссылки «Подробнее» → `/docs/*.md`
- Bind по умолчанию: `127.0.0.1`

---

## 10. Тестирование

```bash
pip install -e ".[kb,dev]"
pytest -q
# 259 passed
./scripts/run_tests.sh
```

| Набор | Назначение |
|-------|------------|
| `tests/kb/` | **122** тестов KB (API, guards, indexer) |
| `tests/test_integration_dashboard.py` | Статусы §6.4, export/import, `/docs/` |
| `tests/test_mcp_*.py`, `test_mcp_section.py` | Compose, naming, порты 82xx, API §2 |
| `tests/test_kb_ports.py` | Порты 83xx, `allocate_http_port` |
| `tests/test_plugins.py` | VSIX install matrix + batch API |
| `tests/test_rules_*.py` | EDT/XML, create_metadata, 409, MCP text |
| `tests/test_acceptance_tz15.py` | Мета-пороги ТЗ §15 |

CI: `.github/workflows/tests.yml` (Python 3.11–3.13).

Фикстуры (`tests/conftest.py`):

- XML: `ONEC_XML_FIXTURE` или `~/Desktop/ДиректорияКурсора/ТестоваяВыгрузка`
- EDT: `ONEC_EDT_FIXTURE` или `~/Desktop/EDT-fixture`

---

## 11. Документация §22

| Файл | Статус |
|------|--------|
| `README.md` | ✅ Quick start, Attributions, CLI, тесты |
| `docs/README.md` | ✅ Оглавление, карта API, правила сопровождения |
| `docs/01-plugins.md` | ✅ §1 |
| `docs/02-mcp-docker.md` | ✅ §2 |
| `docs/03-knowledge-base.md` | ✅ §3 |
| `docs/04-rules-generator.md` | ✅ §4 |
| `docs/05-cursor-mcp-setup.md` | ✅ mcp.json |
| `docs/errors/mcp-docker.json` | ✅ UI modal §2 |
| `docs/AGENT_HANDOFF.md` | ✅ этот файл |
| `docs/kb/DEPLOYMENT_TLS.md` | ✅ admin |
| `docs/kb/EDT_FORMS_AUDIT.md` | ✅ разработчик |
| `CHANGELOG.md` | ✅ история 0.1.0–1.0.0 |

При изменении API — обновлять соответствующий user doc + этот файл.

---

## 12. Ограничения для агентов

1. **Не** запускать `docker compose up` на машине заказчика без явного запроса.
2. **Не** править `~/DockerMCP/` и существующие контейнеры при разработке.
3. Python **3.13** (минимум 3.11).
4. Синтаксис 1С — проверять через MCP `1c-syntax-helper`, не выдумывать API.

---

*Обновлено после шага 9 (финализация документации §22, релиз v1.0.0).*
