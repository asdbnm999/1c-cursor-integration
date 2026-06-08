# Production: TLS и reverse proxy

`kb-web` по умолчанию слушает **127.0.0.1:5050** без TLS. Для доступа по HTTPS используйте reverse proxy на том же хосте.

## Архитектура

```
Клиент (HTTPS) → nginx/Caddy (:443) → kb-web (127.0.0.1:5050)
MCP Docker     → остаётся на 127.0.0.1:8010 (не публикуйте наружу без необходимости)
```

Индексация и Chroma остаются на хосте; проксируется только Flask UI/API.

## nginx

Пример: [`deploy/nginx/kb-web.conf`](../deploy/nginx/kb-web.conf)

```bash
sudo cp deploy/nginx/kb-web.conf /etc/nginx/sites-available/kb-web
sudo ln -s /etc/nginx/sites-available/kb-web /etc/nginx/sites-enabled/
sudo certbot --nginx -d kb.example.com
sudo nginx -t && sudo systemctl reload nginx
```

Запуск приложения:

```bash
export KB_API_TOKEN="длинный-секрет"   # обязательно при доступе извне
kb-web --host 127.0.0.1 --port 5050 --no-browser
```

## Caddy (авто-TLS)

Пример: [`deploy/Caddyfile`](../deploy/Caddyfile)

```bash
caddy run --config deploy/Caddyfile
```

## Заголовки и API-токен

При `KB_API_TOKEN` клиент передаёт:

```
Authorization: Bearer <token>
```

В веб-UI: поле «API-токен» в шапке (сохраняется в `sessionStorage`).

nginx пробрасывает заголовки:

```nginx
proxy_set_header Authorization $http_authorization;
proxy_set_header X-KB-API-Token $http_x_kb_api_token;
```

## Чек-лист production

- [ ] `kb-web` только на loopback (`127.0.0.1`)
- [ ] `KB_API_TOKEN` задан
- [ ] TLS 1.2+ на reverse proxy
- [ ] MCP-порты (8010+) не открыты в firewall
- [ ] `MAX_CONTENT_LENGTH` 512 MB — ограничьте upload на proxy при необходимости
