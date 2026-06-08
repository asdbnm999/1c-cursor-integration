# Векторная база знаний проекта

Раздел **§3** веб-приложения 1C:Cursor: локальная векторная база **вашей** конфигурации 1С (EDT / XML). Индексация выполняется на **хосте**, MCP-сервер поиска — в **Docker**.

**URL:** http://127.0.0.1:8080/kb/  
**API:** `/kb/api/*`  
**Подробнее (техн.):** [docs/kb/ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md](kb/ОПИСАНИЕ_И_ВНЕДРЕНИЕ.md)

---

## Модель

| Сущность | Описание |
|----------|----------|
| **Профиль** | Одна конфигурация 1С |
| **Chroma collection** | Один индекс на профиль |
| **MCP** | Ключ `1c-kb-<имя>` в `mcp.json` |
| **Порт** | **8301+** (1-й профиль → 8301, 2-й → 8302, …) |
| **Docker stack** | `1c-kb-<имя>-mcp` |

---

## Workflow (3 шага)

```
1. Индексация (chunks > 0)
       ↓
2. Docker (build + up контейнера)
       ↓
3. MCP apply (запись в mcp.json)
```

Каждый следующий шаг блокируется, пока не выполнен предыдущий (см. badges «Не выполнено» на странице профиля).

---

## Мастер первого профиля

На странице `/kb/` — collapsible **«Мастер первого профиля»** (5 шагов):

1. Путь к EDT или XML-выгрузке  
2. Анализ (preview, ETA)  
3. Настройки (формы, embeddings, docs/)  
4. Создание профиля  
5. Запуск индексации  

Быстрый путь: кнопка **«+ Новый профиль»**.

---

## Индексация

| Режим | CLI | UI |
|-------|-----|-----|
| Полная | `1c-cursor-kb-index --profile X --full` | «Полная индексация» |
| Resume | `--full --resume` | «Продолжить» |
| Инкремент | `--incremental` | «Обновить индекс» |
| Watch | `config.yaml` | Toggle на странице профиля |

**Форматы:** EDT (`.project` + `src/`), XML (`Configuration.xml` в корне).

**Embeddings:** local `multilingual-e5-small` (default) или OpenAI; device `auto|cpu|cuda|mps`.

**HF cache:** `data/hf_cache/` (фиксированный путь в monorepo).

---

## Docker профиля

### Сборка образа KB

По умолчанию (без ручной настройки):

- `setuptools` / `wheel` / `certifi` — **офлайн** из `bootstrap-wheels/`.
- Зависимости MCP — из `requirements-kb-mcp.txt` (без Flask); основной индекс **pypi.org**, запасной — **mirror.yandex.ru**.
- Пакет `1c-cursor` — `pip install --no-deps -e .` (только entry point `1c-cursor-kb-mcp`).

Первая сборка: **15–30 мин** (torch, chromadb). Включите «Пересобрать образ» после `git pull`.

- Compose генерируется в `{docker_root}/1c-kb-<profile>/` (default `~/DockerMCP/1c-kb-<profile>/`)
- Образ: `1c-kb-<profile>-mcp:latest`
- Контейнер: `1c-kb-<profile>-mcp`, порт **83xx:8000**
- Volumes: `data/` + `profiles/` (read-only в контейнер)

После deploy: **Cursor → Settings → MCP → Refresh**.

Merge `mcp.json` — через единый модуль `web/cursor_mcp.py` (не затирает другие серверы).

---

## MCP tools (8 штук)

| Tool | Назначение |
|------|------------|
| `search_project` | Гибридный / векторный поиск |
| `get_object` | Карточка объекта метаданных |
| `get_module_summary` | Сводка BSL-модуля |
| `list_subsystems` | Подсистемы |
| `find_references` | Ссылки на идентификатор |
| `list_object_modules` | Модули объекта |
| `search_by_subsystem` | Объекты подсистемы |
| `get_register_movements` | Движения регистра |

URL: `http://127.0.0.1:83xx/mcp`

---

## Export / import

- **Экспорт:** архив `.tar.gz` **с индексами** (кнопка на странице профиля)
- **Импорт:** «Импортировать архив…» на `/kb/`
- Перенос на другой ПК: распакуйте профиль, поднимите Docker, apply MCP

---

## Связь с §4 (Правила)

На странице профиля: **«Сгенерировать правила для этого проекта»** → `/rules/?project_path=<корень проекта>`.

---

## Защита API

Опционально: переменная окружения `KB_API_TOKEN`.  
Тогда все запросы к `/kb/api/*` требуют заголовок `Authorization: Bearer …` или `X-KB-API-Token`.  
Страницы `/kb/` доступны без токена; токен можно задать в UI (диалог «Защита API»).

---

## CLI

```bash
1c-cursor-kb-index --profile NAME --full [--resume] [--progress]
1c-cursor-kb-index --profile NAME --incremental
1c-cursor-kb-index --profile NAME --export backup.tar.gz
1c-cursor-kb-index --profile NAME --import backup.tar.gz --overwrite
1c-cursor-kb-mcp   # debug на хосте
```

Deprecated: `kb-index`, `kb-mcp` (warning в stderr).

---

## Troubleshooting

| Симптом | Действие |
|---------|----------|
| Docker badge «недоступен» | Запустите Docker Desktop |
| Индексация не стартует | Проверьте путь проекта, scan |
| MCP не в Cursor | Apply mcp.json + Refresh MCP |
| Порт занят | При запуске контейнера — ошибка; смените `port` в config профиля |
| Мало RAM | Уменьшите batch embeddings, закройте другие стеки |

Подробнее: [kb/AGENT_HANDOFF.md](kb/AGENT_HANDOFF.md), [kb/DEPLOYMENT_TLS.md](kb/DEPLOYMENT_TLS.md).
