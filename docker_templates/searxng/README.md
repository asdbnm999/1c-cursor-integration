# Шаблон SearXNG MCP

Генерация выполняется модулем `web/mcp_compose.py` → `generate_searxng_files()`.

Итоговые файлы в `{docker_root}/searxng/`:

- `docker-compose.yml` — project `searxng-mcp`, services `searxng-mcp-valkey`, `searxng-mcp-core`, `searxng-mcp`
- `.env` — `SEARXNG_VERSION`, `SEARXNG_PORT`
- `core-config/settings.yml` — `search.formats` включает `json`

Порты по умолчанию: MCP **8201**, Core **8202**.
