# Стандартные MCP-серверы (Docker)

Раздел **§2** веб-приложения 1C:Cursor: локальные MCP через Docker для Cursor IDE.

## Назначение

| Сервер | mcp.json key | Порт (default) | Зачем |
|--------|--------------|----------------|-------|
| SearXNG | `searxng` | 8201 (MCP), 8202 (UI) | Веб-поиск без API-ключей через MCP |
| 1C Syntax Helper | `1c-syntax-helper` | 8203 | Справка платформы из `shcntx_ru.hbk` |

## Быстрый старт

1. Запустите `1c-cursor-web` → откройте http://127.0.0.1:8080/mcp/
2. Убедитесь, что Docker daemon работает (badge в header).
3. Отметьте нужные серверы чекбоксами.
4. Для Syntax — укажите путь к `shcntx_ru.hbk` (обязательно перед Deploy).
5. **Deploy** (compose создаётся автоматически) → **Применить в mcp.json**.
6. Cursor → Settings → MCP → **Refresh**.

## Каталоги Docker

По умолчанию корень: `~/DockerMCP/` (поле `docker.root` в `data/settings.json`).  
На странице `/mcp/` блок **«Корень Docker»** — поле ввода, **Выбрать…**, **Сохранить**, **По умолчанию**.

| Стек | Каталог по умолчанию |
|------|----------------------|
| SearXNG | `{docker_root}/searxng/` |
| 1C Syntax | `{docker_root}/1c-syntax/` |

Каталог **конкретного стека** можно переопределить кнопкой **«Выбрать каталог…»** на карточке сервера.

**Не используйте** устаревший `~/DockerMCP/docker-compose.yml` — только отдельные подкаталоги.

## Именование контейнеров (§7.2)

| Уровень | Пример SearXNG |
|---------|----------------|
| Compose project | `searxng-mcp` |
| MCP service/container | `searxng-mcp` |
| Auxiliary | `searxng-mcp-valkey`, `searxng-mcp-core` |

Ключ в `mcp.json` **без** суффикса `-mcp`: `searxng`, `1c-syntax-helper`.

## Порты

Схема `8RRNN` для §2 → `82xx`:

- **8201** — SearXNG MCP (`http://127.0.0.1:8201/mcp`)
- **8202** — SearXNG Core UI
- **8203** — 1C Syntax MCP (`http://127.0.0.1:8203/mcp`)

Перед deploy проверяйте конфликты на dashboard и в §2.

## Ресурсы

| Пресет | Valkey | Core | SearXNG MCP | ES heap | Syntax MCP |
|--------|--------|------|-------------|---------|------------|
| Экономный | 128m | 384m | 256m | 512m | 512m |
| Расширенный | 256m | 768m | 512m | 1024m | 1024m |

Ручной режим — ползунки в UI. Верхняя граница ограничивается `docker info` (RAM Docker).

## SearXNG

1. Генерация: `docker-compose.yml`, `.env`, `core-config/settings.yml`
2. `secret_key` — генерируется автоматически при первом deploy
3. В `search.formats` обязателен `json`
4. Deploy: `docker compose pull && docker compose up -d`
5. Health: `http://127.0.0.1:8201/health` (внутри контейнера — **127.0.0.1**, не localhost)

External volume (миграция): `dockermcp_core-data`.

## 1C Syntax Helper

1. `git clone` репозитория в `{syntax_dir}/1c-syntax-helper-mcp/`
2. Патч `mcp.py`: `ping`, `notifications/cancelled`, `resources/list`
3. HBK: bind mount **каталога** файла (без копирования в репо)
4. `docker compose build && docker compose up -d`
5. Ожидание индекса: `/index/status` → completed (до 5 мин)
6. Post-deploy: MCP ping + notifications/cancelled

External volume: `dockermcp_es-1c-data`.

## Статус раздела «Готово»

- Каждый **отмеченный** сервер: контейнер Up, health OK, запись в mcp.json с верным URL
- Если **ни один** чекбокс — «Не начато»

Статус отображается на карточке §2 на [dashboard](/) и в мастере первого запуска.

## Диагностика на dashboard

| Элемент | Назначение |
|---------|------------|
| Docker badge | Daemon up/down |
| RAM estimate | Сумма пресетов стеков §2 + KB (подстроки по стекам) |
| Панель MCP | Статус серверов из `mcp.json`, кнопка «Проверить MCP» |

Конфликт портов проверяется при **Deploy** (§2) и **запуске контейнера** (§3 KB); на странице §2 MCP — предупреждения в шапке. Подробнее: [05-cursor-mcp-setup.md](05-cursor-mcp-setup.md).

## Типовые ошибки

Кнопка «Типовые ошибки» в UI; каталог: `docs/errors/mcp-docker.json`.

## API

Префикс `/mcp/api/`: `status`, `generate-compose`, `deploy`, `stop`, `logs`, `errors`, `settings`, `apply-mcp`, `preview-mcp`, `orphans`.

## См. также

- [Настройка mcp.json](05-cursor-mcp-setup.md)
- ТЗ §10, `MCP-Docker-сборка-и-фиксы.md`
