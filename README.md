# 1C:Cursor

Единое кроссплатформенное веб-приложение для настройки среды разработки конфигураций 1С в **Cursor IDE**.

**Версия:** 1.0.0  
**Документация:** [docs/README.md](docs/README.md)  
**Для AI-агентов:** [docs/AGENT_HANDOFF.md](docs/AGENT_HANDOFF.md)

---

## Что это

Один веб-сервер (`http://127.0.0.1:8080`) объединяет четыре независимых раздела:

| § | URL | Назначение | Документация |
|---|-----|------------|--------------|
| 1 | `/plugins/` | Установка VSIX (BSL, дерево конфигурации) | [01-plugins.md](docs/01-plugins.md) |
| 2 | `/mcp/` | Docker: SearXNG + 1C Syntax Helper | [02-mcp-docker.md](docs/02-mcp-docker.md) |
| 3 | `/kb/` | Векторная база знаний вашей конфигурации | [03-knowledge-base.md](docs/03-knowledge-base.md) |
| 4 | `/rules/` | Генерация markdown-правил для AI | [04-rules-generator.md](docs/04-rules-generator.md) |

На **dashboard** (`/`): статусы разделов, диагностика Docker/RAM, оценка RAM MCP-стеков, проверка MCP, мастер первого запуска, экспорт/импорт настроек.

---

## Быстрый старт

### Требования

| Компонент | Минимум |
|-----------|---------|
| Python | 3.11+ (рекомендуется 3.13) |
| Docker | Engine 24+, Compose v2 — для §2 и §3 |
| Cursor IDE | Установленный редактор |
| RAM | 8 GB (16 GB+ при нескольких MCP-стеках) |

### Установка

```bash
cd 1c-cursor
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e ".[kb,dev]"
1c-cursor-web
```

Браузер откроется автоматически на **http://127.0.0.1:8080** (отключить: `1c-cursor-web --no-browser`).

> Для §3 (KB) нужен extra `[kb]`: chromadb, sentence-transformers и др. Команда выше устанавливает всё сразу.

### Рекомендуемый порядок настройки

1. **§1 Плагины** — установите оба bundled VSIX (`/plugins/`).
2. **§2 MCP** — включите SearXNG и/или Syntax, сгенерируйте compose, deploy, apply `mcp.json`. Для Syntax укажите путь к `shcntx_ru.hbk`.
3. **§3 KB** — создайте профиль, проиндексируйте проект EDT/XML, поднимите Docker, apply MCP.
4. **§4 Правила** — сгенерируйте `.md` в `.cursor/rules/` проекта.
5. **Cursor** → Settings → MCP → **Refresh**.

Подробнее: [docs/05-cursor-mcp-setup.md](docs/05-cursor-mcp-setup.md).

---

## CLI

| Команда | Описание |
|---------|----------|
| `1c-cursor-web` | Веб-UI на `:8080` |
| `1c-cursor-kb-index --profile NAME --full` | Полная индексация профиля KB |
| `1c-cursor-kb-index --profile NAME --incremental` | Инкрементальное обновление |
| `1c-cursor-kb-index --profile NAME --export backup.tar.gz` | Экспорт с индексами |
| `1c-cursor-kb-mcp` | Отладка MCP KB на хосте |

Устаревшие алиасы (warning): `kb-index`, `kb-mcp`.

---

## Тестирование

```bash
./scripts/run_tests.sh
# или
pytest -q
```

**256 passed** (+3 skipped без локальных фикстур 1С). CI: `.github/workflows/tests.yml` (Python 3.11–3.13).

---

## Структура репозитория

```
1c-cursor/
├── web/                 # Flask: app, routes, sections, cursor_mcp
├── packages/
│   ├── kb/              # Индексатор, MCP server, Docker (vendored)
│   └── rules/           # Парсер правил (vendored)
├── assets/extensions/   # Bundled VSIX
├── docker_templates/    # Шаблоны compose §2
├── data/                # Runtime (gitignore): settings, profiles, hf_cache
├── profiles/_template/  # Шаблон config.yaml профиля KB
├── tests/               # pytest (256+)
├── scripts/run_tests.sh
└── docs/                # Пользовательская и техническая документация §22
```

---

## Порты и Docker

| Зона | Порты | Назначение |
|------|-------|------------|
| §2 | 8201, 8202, 8203 | SearXNG MCP, Core, 1C Syntax MCP |
| §3 | 8301+ | KB-профили (`8300+N`) |

Корень Docker по умолчанию: `~/DockerMCP/`. Имена контейнеров: `{slug}-mcp` (см. [02-mcp-docker.md](docs/02-mcp-docker.md)).

---

## Лицензия

Proprietary — инструмент настройки 1C:Cursor.

История изменений: [CHANGELOG.md](CHANGELOG.md).

---

## Правообладатели bundled VSIX

Расширения в `assets/extensions/` предоставляются их авторами. Вы можете заменить файлы собственными копиями.

### 1c-configuration-tree (v2.10.7)

| Поле | Значение |
|------|----------|
| Файл | `1c-configuration-tree-2.10.7.vsix` |
| Publisher | whiterabbit |
| Display name | 1C Configuration tree |
| License | MIT |
| Author | Andrey Ponomarev |
| Repository | https://github.com/asweetand-a11y/MetadataViewer1C |

### Language 1C (BSL) (v1.33.2)

| Поле | Значение |
|------|----------|
| Файл | `1c-syntax.language-1c-bsl-1.33.2.vsix` |
| Publisher | 1c-syntax |
| Display name | Language 1C (BSL) |
| License | SEE LICENSE IN LICENSE.md |
| Repository | https://github.com/1c-syntax/vsc-language-1c-bsl |
