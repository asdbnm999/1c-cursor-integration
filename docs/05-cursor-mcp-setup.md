# Настройка mcp.json в Cursor

Модуль `web/cursor_mcp.py` объединяет MCP-серверы из разделов §2 и §3 в единый конфиг Cursor.

## Расположение файла

| ОС | Типичный путь |
|----|---------------|
| macOS / Linux | `~/.cursor/mcp.json` |
| Альтернатива | `~/Library/Application Support/Cursor/User/globalStorage/mcp.json` |

Путь можно переопределить в `data/cursor-settings.json` → `mcp_config_path`.

## Формат

```json
{
  "mcpServers": {
    "searxng": { "url": "http://127.0.0.1:8201/mcp" },
    "1c-syntax-helper": { "url": "http://127.0.0.1:8203/mcp" },
    "1c-kb-myproject": { "url": "http://127.0.0.1:8301/mcp" }
  }
}
```

**Важно:** используйте `127.0.0.1`, не `localhost` (меньше проблем с IPv6 на macOS).

## Merge без затирания

`merge_servers()` обновляет только ключи, которые добавляет 1C:Cursor. Сторонние серверы сохраняются.

## Preview и бэкапы

1. **Preview diff** — показ изменений до записи
2. При записи — бэкап в `data/cursor-mcp-backups/`
3. TTL бэкапов: **3 дня**

## После apply

1. Cursor → **Settings → MCP → Refresh** (или перезапуск Cursor)
2. Проверьте статус серверов в панели MCP на dashboard

## Ключи по разделам

| Раздел | Ключ | Когда добавляется |
|--------|------|-------------------|
| §2 SearXNG | `searxng` | Deploy + apply в §2 |
| §2 Syntax | `1c-syntax-helper` | Deploy + apply в §2 |
| §3 KB | `1c-kb-<имя профиля>` | MCP apply на странице профиля |

§4 (правила) **не** попадает в mcp.json.

## Health-check

Dashboard → «Проверить MCP» вызывает `check_all_mcp_servers()`:
- HTTP `/health` на origin
- GET/HEAD на URL `/mcp`

Для 1C Syntax после deploy дополнительно проверяются `ping` и `notifications/cancelled`.

## Несколько KB-профилей

Если активно более одного `1c-kb-*`, в сгенерированных правилах (§4) AI должен спрашивать, какую базу использовать в начале диалога.

## Экспорт и перенос настроек

На dashboard: **«Экспорт JSON»** / **«Импорт JSON»** — настройки 1C:Cursor (без Chroma-индексов).

Архив KB с индексами: `/kb/` → экспорт профиля `.tar.gz` (см. [03-knowledge-base.md](03-knowledge-base.md)).

## Восстановление mcp.json

- Бэкапы: `data/cursor-mcp-backups/` (TTL 3 дня)
- KB: `/kb/api/cursor/mcp/restore` — восстановление из бэкапа

## См. также

- [MCP Docker](02-mcp-docker.md)
- ТЗ §8
