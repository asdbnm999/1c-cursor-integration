# Шаблон 1C Syntax Helper MCP

Генерация: `web/mcp_compose.py` → `generate_syntax_files()`.

Итог в `{docker_root}/1c-syntax/`:

- `docker-compose.yml` — project `1c-syntax-helper-mcp`
- `1c-syntax-helper-mcp/` — git clone `https://github.com/Antonio1C/1c-syntax-helper-mcp.git`

Deploy pipeline (`web/mcp/deploy.py`):

1. `git clone` (если нет)
2. Патч `src/api/routes/mcp.py` (ping, cancelled, resources)
3. `docker compose build 1c-syntax-helper-mcp && up -d`

Порт MCP по умолчанию: **8203** → контейнер `:8000`.
