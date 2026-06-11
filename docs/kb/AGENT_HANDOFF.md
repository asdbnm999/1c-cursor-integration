# project-kb-mcp — полная документация для агента / разработчика

**Версия:** 0.1.0 · **Дата:** июнь 2026  
**Назначение:** единый справочник по архитектуре, коду, API, workflow и правилам разработки. Передайте этот файл другому агенту как точку входа.

---

## 1. Что это за проект

**project-kb-mcp** — локальная векторная база знаний для конфигураций 1С (EDT или XML-выгрузка) с MCP-сервером для Cursor IDE.

| Компонент | Где работает | Роль |
|-----------|--------------|------|
| **kb-web** | Хост (Flask, :5050) | UI, API, фоновые job индексации, watch |
| **kb-index** | Хост (CLI) | Полная/инкрементальная индексация, export/import |
| **kb-mcp** | Docker-контейнер на профиль | HTTP MCP tools, чтение Chroma |
| **ChromaDB** | `data/profiles/<name>/chroma` | Векторное хранилище |
| **Keyword / References** | `data/profiles/<name>/indexes/` | Гибридный поиск, ссылки в BSL |

**Ключевая модель:** один **профиль** = одна конфигурация 1С = одна коллекция Chroma = один MCP-сервер = один HTTP-порт.

**Разделение нагрузки:** индексация и эмбеддинги — на хосте; контейнер MCP только отдаёт поиск (read-only к индексу через volume).

---

## 2. Быстрый старт

```bash
cd project-kb-mcp
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,cli]"
kb-web   # → http://127.0.0.1:5050
```

**Требования:** Python 3.11+, Docker Desktop, ~8 GB RAM для крупных баз с локальными эмбеддингами.

**Тесты (обязательны перед изменениями):**

```bash
pytest tests/ -q
# Ожидается: 122 passed
```

После тестов pytest **автоматически удаляет** артефакты в `data/profiles/` и `profiles/` (см. `tests/conftest.py`, `TEST_DATA_PROFILE_DIRS`).

---

## 3. Структура репозитория

```
project-kb-mcp/
├── indexer/           # Ядро: индексация, поиск, Docker, jobs, MCP-конфиг
├── mcp_server/        # FastMCP HTTP-сервер (tools для Cursor)
├── web/               # Flask UI + REST API
│   ├── app.py
│   ├── static/js/app.js
│   ├── static/css/app.css
│   └── templates/
├── tests/             # 37 test_*.py + conftest + fixtures/
├── scripts/           # CLI-утилиты (не entry points)
├── docker/            # Dockerfile + entrypoint.sh для MCP-образа
├── deploy/            # nginx/Caddy примеры для production TLS
├── profiles/          # Конфиги профилей (YAML), в git только _template/
├── data/              # Runtime-данные (в .gitignore)
│   ├── profiles/<name>/   # chroma, indexes, manifest, jobs
│   ├── docker/<name>/     # логи сборки образа
│   ├── cursor-mcp-backups/  # бэкапы mcp.json (вне ~/.cursor)
│   ├── hf_cache/          # кэш HuggingFace
│   └── cursor-settings.json  # путь к каталогу Cursor (если нет ~/.cursor)
├── docs/              # Документация
├── pyproject.toml     # entry points: kb-index, kb-mcp, kb-web
└── README.md
```

### Что НЕ в git (.gitignore)

- Весь `data/`
- `profiles/*` кроме `profiles/_template/`
- `.venv/`, `__pycache__/`, `.pytest_cache/`, `*.egg-info/`

---

## 4. Пути и данные профиля

| Что | Путь |
|-----|------|
| Конфиг профиля | `profiles/<name>/config.yaml` |
| Chroma | `data/profiles/<name>/chroma/` |
| Keyword index | `data/profiles/<name>/indexes/keyword/` |
| References index | `data/profiles/<name>/indexes/references/` |
| Manifest | `data/profiles/<name>/index-manifest.json` |
| Checkpoint | `data/profiles/<name>/index-checkpoint.json` |
| Last job | `data/profiles/<name>/last-job.json` |
| MCP merge cache | `data/profiles/<name>/mcp-merged.json` |
| Docker build log | `data/docker/<name>/build.log` |
| Compose-проект | `~/DockerMCP/1c-kb-<name>/` (генерируется, не в репо) |

Шаблон конфига: `profiles/_template/config.yaml`.

---

## 5. Жизненный цикл профиля (workflow)

Порядок шагов **обязателен** — реализованы guard-правила в UI и API.

```
1. Индексация (chunks > 0)
       ↓
2. Docker (сборка образа + запуск контейнера)
       ↓
3. Подключение MCP (запись в mcp.json Cursor)
```

### Guards (`indexer/workflow_guards.py`)

| Guard | Условие | Блокирует |
|-------|---------|-----------|
| `require_indexed_profile` | `count_chunks == 0` | Все mutating Docker API |
| `require_container_for_mcp` | `container_id` пуст | MCP apply/merge/download |

В API ответе профиля: `gates.docker_enabled`, `gates.mcp_enabled`.

### Docker-именование (`indexer/docker_names.py`)

- Образ и контейнер: `1c-kb-<profile>-mcp`
- Внутренний порт контейнера: `8000`
- Host port: из `config.mcp.port` (обычно 8010+)

---

## 6. Модули indexer/ (карта ответственности)

| Модуль | Назначение |
|--------|------------|
| `config.py` | Загрузка/сохранение `ProfileConfig` из YAML |
| `profiles.py` | `list_profiles`, пути, `PROJECT_ROOT` |
| `scanner.py` | Обход EDT/XML, определение формата |
| `extract_*.py` | BSL, metadata, docs, subsystems |
| `chunkers.py` | Разбиение на чанки с overlap |
| `embeddings.py` | Local (sentence-transformers) / OpenAI |
| `store.py` | Chroma: add/query/count |
| `keyword_index.py` | BM25-подобный индекс |
| `reference_index.py`, `references.py` | Поиск ссылок в BSL |
| `hybrid_search.py` | Vector + keyword |
| `pipeline.py` | CLI `kb-index` |
| `incremental.py` | Инкремент по изменённым файлам |
| `git_changes.py`, `local_changes.py` | Источники изменений |
| `jobs.py` | Фоновые job, persist, SSE |
| `checkpoint.py` | Resume полной индексации |
| `watcher.py` | Watch/poll авто-инкремент |
| `wizard.py` | Мастер preview/оценка времени |
| `profile_ops.py` | create/delete/clone профиля |
| `profile_compare.py`, `bsl_compare.py` | Сравнение профилей |
| `index_archive.py` | Export/import `.tar.gz` |
| `docker_build.py` | Сборка образа через kb-web |
| `docker_compose.py` | Генерация `docker-compose.yml` |
| `docker_manager.py` | start/stop/status/logs |
| `docker_names.py` | Имена image/container |
| `mcp_registry.py` | Парсинг/merge `mcp.json` |
| `cursor_mcp_config.py` | Apply/restore MCP, бэкапы (3 дня TTL) |
| `cursor_mcp_status.py` | Статус подключения в Cursor |
| `workflow_guards.py` | Блокировки шагов workflow |
| `workflow_status.py` | Прогресс 4 шагов на главной |
| `health.py` | Системный и профильный health |
| `api_auth.py` | `KB_API_TOKEN` для `/api/*` |
| `api_errors.py` | Единый формат ошибок Flask |
| `native_dialogs.py` | Выбор папки (macOS/другие ОС) |

---

## 7. MCP tools (`packages/kb/mcp_server/server.py`)

**Поверхность: ровно 5 методов.** Эти tools автоматически попадают в генерируемые правила Cursor через `packages/rules/mcp_rules.py` (§4 Rules).


| Tool | Описание |
|------|----------|
| `search_project` | Семантический / гибридный поиск; в ответе тип совпадения: metadata / bsl / query_text |
| `get_object` | Карточка объекта; `detail`: brief \| structure \| movements \| posting \| full |
| `list_by_relation` | Связи: documents_by_register, registers_by_document, references_to_object, objects_in_subsystem |
| `get_module` | Чтение BSL: `mode` = summary \| procedure \| event \| fragment |
| `find_references` | Ссылки на идентификатор; `scope`: all \| metadata \| bsl \| queries |

### Матрица «вопрос → метод»

| Вопрос | Метод | Параметры |
|--------|-------|-----------|
| Где в конфигурации про X? | `search_project` | `query` |
| Что за объект? | `get_object` | `detail="brief"` |
| Реквизиты, ТЧ, измерения? | `get_object` | `detail="structure"` |
| Какие регистры двигает документ? | `get_object` | `detail="movements"` |
| Как проводится? | `get_object` | `detail="posting"` |
| Кто двигает регистр? | `list_by_relation` | `documents_by_register` |
| Где используется имя? | `find_references` | `identifier`, `scope` |
| Покажи процедуру | `get_module` | `mode="procedure"` или `"event"` |
| Что в подсистеме? | `list_by_relation` | `objects_in_subsystem` |

**KB-индекс:** `data/profiles/<name>/indexes/kb/index.json` (строится при полной индексации).

Запуск в контейнере: `KB_PROFILE=<name>` → `entrypoint.sh` → `1c-cursor-kb-mcp --transport http --port 8000`.

---

## 8. REST API (kb-web)

Базовый URL: `http://127.0.0.1:5050`

### Система

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/system` | Docker available, api_token_required |
| GET | `/api/health` | Сводка по всем профилям |
| GET | `/api/cursor/settings` | Каталог Cursor, бэкапы mcp.json |
| PUT | `/api/cursor/dir` | Сохранить каталог Cursor |
| POST | `/api/cursor/mcp/restore` | Восстановить mcp.json из бэкапа |

### Профили

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/profiles` | Список профилей |
| POST | `/api/profiles` | Создать профиль |
| GET | `/api/profiles/<name>` | Сводка (+ gates, workflow, docker, cursor_mcp) |
| DELETE | `/api/profiles/<name>` | Полное удаление |
| POST | `/api/profiles/<name>/scan` | Тестовое сканирование |
| POST | `/api/profiles/<name>/index` | Запуск job (full/incremental/resume) |
| GET | `/api/profiles/<name>/index/changes` | Preview инкремента |
| GET/DELETE | `/api/profiles/<name>/checkpoint` | Checkpoint |
| GET | `/api/jobs/<id>` | Статус job |
| GET | `/api/jobs/<id>/stream` | SSE прогресс |
| POST | `/api/jobs/<id>/cancel` | Отмена |

### Docker (требует `gates.docker_enabled`)

| Метод | Путь |
|-------|------|
| GET/POST | `/api/profiles/<name>/docker/build` |
| PUT | `/api/profiles/<name>/docker/compose-dir` |
| POST | `/api/profiles/<name>/docker/start` |
| POST | `/api/profiles/<name>/docker/stop` |
| GET | `/api/profiles/<name>/docker/logs` |

### MCP (mutating требует `gates.mcp_enabled`)

| Метод | Путь |
|-------|------|
| POST | `/api/profiles/<name>/mcp/apply` |
| POST | `/api/profiles/<name>/mcp/merge` |
| GET | `/api/profiles/<name>/mcp/download` |
| GET | `/api/profiles/<name>/mcp/cursor-status` |

### Прочее

- `POST /api/wizard/preview` — мастер onboarding
- `POST /api/profiles/import`, `POST /api/profiles/<name>/export`
- `POST /api/profiles/compare`, `POST /api/profiles/<name>/clone`
- `PUT /api/profiles/<name>/embeddings`, `PUT /api/profiles/<name>/indexing`
- `POST /api/profiles/<name>/watch/start|stop`

**Авторизация:** если задан `KB_API_TOKEN`, все `/api/*` требуют `Authorization: Bearer <token>`. В UI — `sessionStorage.kb_api_token`.

---

## 9. Веб-интерфейс

| Файл | Содержимое |
|------|------------|
| `templates/index.html` | Список профилей, health, **onboarding wizard (развёрнут по умолчанию)** |
| `templates/profile.html` | 3 шага: Индексация → Docker → Cursor MCP |
| `templates/base.html` | Topbar, диалог «Защита API» |
| `static/js/app.js` | Вся клиентская логика (~1750 строк) |
| `static/css/app.css` | Стили, workflow steps, modals |

Ключевые JS-функции:
- `initDashboard()` — главная
- `initProfilePage(name)` — страница профиля
- `updateWorkflowGates(p)` — блокировка Docker/MCP
- `refreshProfile(name)` — polling статуса
- `initDialogScrollLock()` — блокировка скролла фона при `<dialog open>`

---

## 10. CLI

```bash
kb-index --profile NAME --full              # полная индексация
kb-index --profile NAME --full --resume     # продолжить с checkpoint
kb-index --profile NAME --incremental       # по изменённым файлам
kb-index --profile NAME --preview-changes
kb-index --profile NAME --export FILE.tar.gz
kb-index --profile NAME --import FILE.tar.gz --overwrite

python scripts/create_profile.py            # создание профиля из CLI
python scripts/register_mcp.py --profile NAME
python scripts/benchmark_search.py --profile NAME
python scripts/test_queries.py --profile NAME  # queries.txt в profiles/<name>/
```

---

## 11. Cursor / mcp.json

1. Каталог Cursor: `~/.cursor` или пользовательский (`data/cursor-settings.json`).
2. Apply: merge сервера `1c-kb-<profile>` в `mcp.json` без затирания других серверов.
3. Бэкап перед записью: `data/cursor-mcp-backups/mcp.json.bak-YYYYMMDD-HHMMSS`.
4. Бэкапы старше **3 дней** удаляются автоматически.
5. Restore: кнопка «Отменить — из бэкапа» или `POST /api/cursor/mcp/restore`.

Режимы UI: авто (apply одной кнопкой) / ручной (merge + download). Переключатель в `localStorage.kb_mcp_update_mode`.

---

## 12. Индексация — важные детали

### Форматы

- **edt:** корень с `src/*.mdo`
- **xml_export:** XML-выгрузка конфигурации

### `include_forms`

Если `true` — индексируются модули форм (EDT и XML). См. `docs/EDT_FORMS_AUDIT.md`.

### Embeddings

- **local:** `intfloat/multilingual-e5-small` (default), device `auto|cpu|cuda|mps`
- **openai:** `OPENAI_API_KEY` в окружении kb-web
- Смена модели → нужна полная переиндексация

### Watch

```yaml
watch:
  enabled: false
  mode: poll   # или watchdog (pip install -e ".[watch]")
```

### Крупные базы (БП 3.0)

- 200–250k чанков, 2–6 ч на CPU с e5-small
- Checkpoint + resume при сбое
- `batch_size` 128–256 для ускорения

---

## 13. Docker

1. **Сборка образа** через UI → `indexer/docker_build.py` → `docker build` с тегом `1c-kb-<profile>-mcp`.
2. **Compose** генерируется в выбранную директорию (рекомендация `~/DockerMCP/1c-kb-<profile>/`).
3. Volume монтирует `data/profiles/<name>/` в контейнер read-only.
4. Зелёный статус Docker в UI только при **работающем** контейнере; при готовом образе — «Образ готов — запустите контейнер».

Файлы: `docker/Dockerfile`, `docker/entrypoint.sh`, `indexer/docker_compose.py`.

---

## 14. Тестирование

```bash
pytest tests/ -q
pytest tests/test_api_integration.py -v   # Web API
pytest tests/test_cursor_mcp_apply.py -v  # MCP apply/restore/prune
pytest tests/test_workflow_guards.py -v   # Guards
```

**Фикстуры:** `tests/fixtures/xml_document.xml`, `profile_config.yaml`  
**Профиль тестов:** `test-fixture` (создаётся в `profiles/test-fixture/config.yaml` на время теста, удаляется после).

**Автоочистка после сессии** (`tests/conftest.py`):
- `data/profiles/{test-fixture, imported-fixture, recreate-test, ...}`
- `profiles/{test-fixture, recreate-test, ...}`

Не удаляются пользовательские профили вроде `testbase`, `bp-30`.

---

## 15. Production / безопасность

- По умолчанию kb-web на `127.0.0.1:5050` — только локально.
- TLS: `docs/DEPLOYMENT_TLS.md`, примеры `deploy/nginx/`, `deploy/Caddyfile`.
- `KB_API_TOKEN` — опциональная защита `/api/*`.
- MCP контейнер — только localhost port mapping.

---

## 16. Правила для агента при изменениях

1. **Минимальный diff** — не трогать несвязанный код.
2. **Тесты обязательны** — `pytest tests/ -q` после изменений.
3. **Не коммитить** `data/`, `.env`, секреты.
4. **1C-код** — проверять синтаксис через MCP `1c-syntax-helper` (если доступен).
5. **Workflow guards** — не обходить без явного запроса пользователя.
6. **Имена Docker** — только через `indexer/docker_names.py`.
7. **Бэкапы mcp.json** — только в `data/cursor-mcp-backups/`, не в `~/.cursor`.
8. **Язык UI** — русский.
9. **Коммиты** — только по запросу пользователя.

### Типичные задачи

| Задача | Где смотреть |
|--------|--------------|
| Новый MCP tool | `mcp_server/server.py`, тест в `tests/test_mcp_server.py` |
| Новый API endpoint | `web/app.py`, тест в `tests/test_api_*.py` |
| UI-изменение | `web/templates/`, `web/static/js/app.js` |
| Логика индексации | `indexer/pipeline.py`, `incremental.py`, `chunkers.py` |
| Docker | `docker_manager.py`, `docker_build.py`, `docker_compose.py` |
| Ошибка «35 чанков после пересоздания» | `profile_ops.py`, `_resolve_index_job` в `web/app.py` |

---

## 17. Связанные документы

| Файл | Содержание |
|------|------------|
| [README.md](../README.md) | Краткий старт |
| [CHANGELOG.md](../CHANGELOG.md) | История изменений |
| [ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md](./ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md) | Подробное руководство пользователя |
| [DEPLOYMENT_TLS.md](./DEPLOYMENT_TLS.md) | nginx/Caddy, TLS |
| [EDT_FORMS_AUDIT.md](./EDT_FORMS_AUDIT.md) | Покрытие include_forms |

---

## 18. Известные ограничения

- Индексация тяжёлая — только на хосте, не в Docker.
- `docker-compose.yml` не в репо — генерируется per-profile.
- Pytest оставляет данные только если сессия прервана до teardown; иначе conftest чистит.
- Пути в `profiles/testbase/config.yaml` машинозависимы — не для git.
- Старые бэкапы в `~/.cursor/mcp.json.bak-*` не мигрируются автоматически.

---

## 19. Entry points (pyproject.toml)

```toml
kb-index = "indexer.pipeline:main"
kb-mcp   = "mcp_server.server:main"
kb-web   = "web.app:main"
```

Optional deps: `[dev]` pytest, `[cli]` tqdm, `[watch]` watchdog.

---

*Конец документа. При расхождении с кодом доверяйте коду и тестам.*
