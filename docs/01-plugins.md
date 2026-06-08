# VS-плагины для 1С

Раздел **§1** приложения 1C:Cursor: установка VSIX-расширений в Cursor для разработки на 1С.

**Маршрут UI:** `/plugins/`  
**API:** префикс `/plugins/api/`

---

## Назначение

Автоматическая установка расширений:

| Bundled VSIX | Назначение |
|--------------|------------|
| `1c-configuration-tree-2.10.7.vsix` | Дерево метаданных конфигурации 1С в sidebar |
| `1c-syntax.language-1c-bsl-1.33.2.vsix` | Подсветка синтаксиса BSL |

Дополнительные `.vsix` можно положить в `assets/extensions/` или добавить через кнопку **«Добавить VSIX…»**.

---

## Каталог расширений Cursor

Приложение определяет каталог автоматически или использует путь из настроек (`data/cursor-settings.json` → `cursor_extensions_dir`).

| ОС | Кандидаты (по приоритету) |
|----|---------------------------|
| **macOS** | `~/Library/Application Support/Cursor/User/extensions/`, `~/.cursor/extensions/` |
| **Windows** | `%USERPROFILE%\.cursor\extensions\`, `%APPDATA%\Cursor\User\extensions\` |
| **Linux** | `~/.cursor/extensions/` |

Если каталог не найден — укажите путь вручную в UI (**«Выбрать…»** или ввод + **«Сохранить путь»**).

---

## Способы установки

### 1. Через CLI Cursor (предпочтительно)

Если `cursor` в PATH и `cursor --version` успешен:

```bash
cursor --install-extension /абсолютный/путь/к/файлу.vsix
```

При переустановке другой версии — с подтверждением в UI добавляется `--force`.

### 2. Вручную (распаковка)

Если CLI недоступен, VSIX распаковывается как ZIP в каталог расширений:

```
{cursor_extensions_dir}/{publisher}.{name}-{version}/
```

---

## Статусы в UI

| Статус | Значение |
|--------|----------|
| Не установлено | Расширение не найдено в каталоге |
| vX.Y.Z | Установлена та же версия, что в VSIX |
| Доступно обновление | В VSIX версия новее установленной |

**Статус раздела (карточка dashboard):**

| Статус | Условие |
|--------|---------|
| Не начато | Ни одно bundled не установлено |
| В процессе | Установлено частично или устаревшая версия |
| Готово | Оба bundled установлены (версия ≥ bundled) |

---

## Конфликт версий

| Ситуация | Действие |
|----------|----------|
| Не установлено | Установить |
| Та же версия | «Уже установлено», пропуск |
| Другая версия | Modal: «Переустановить» / «Пропустить» |
| Batch | Сводка OK / SKIP / FAIL по каждому файлу |

---

## API

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/plugins/api/status` | VSIX, версии, каталог Cursor, статус раздела |
| POST | `/plugins/api/install` | `{ "paths": ["..."], "force": false, "skip_paths": [] }` |
| POST | `/plugins/api/pick-vsix` | Native picker → копия в `assets/extensions/` |
| POST | `/plugins/api/pick-cursor-dir` | Native picker каталога |
| PUT | `/plugins/api/cursor-dir` | `{ "path": "..." }` → `cursor_extensions_dir` |

---

## Troubleshooting

### «Укажите каталог расширений Cursor вручную»

Cursor не установлен или каталог ещё не создан. Запустите Cursor один раз или укажите путь вручную.

### CLI не найден

Установка пойдёт через распаковку. Убедитесь, что каталог расширений существует и доступен на запись.

### Bundled VSIX отсутствует

Положите файлы в `assets/extensions/` из комплекта проекта или с Desktop (см. README Attributions).

### После установки Cursor не видит расширение

Перезапустите Cursor. Проверьте, что папка называется `{publisher}.{name}-{version}`.

---

## Модули кода

| Путь | Роль |
|------|------|
| `web/plugins/vsix.py` | Метаданные VSIX, сканирование установленных |
| `web/plugins/paths.py` | CLI и каталоги по ОС |
| `web/plugins/installer.py` | Установка CLI / manual |
| `web/plugins/service.py` | Статус раздела, API-агрегация |
| `web/plugins/native_dialogs.py` | macOS osascript / tk picker |
| `web/routes/plugins.py` | Flask routes |
| `tests/test_plugins.py` | Unit и API тесты |

---

## Связь с dashboard

Статус §1 на главной странице: **Готово**, когда установлены **оба** bundled VSIX. Частичная установка — «В процессе».

Мастер первого запуска на `/` ведёт на `/plugins/` с отображением текущего статуса.

---

*См. также: [README.md](../README.md), [docs/README.md](README.md), [05-cursor-mcp-setup.md](05-cursor-mcp-setup.md), ТЗ §9.*
