# Аудит поддержки EDT forms (`include_forms`)

**Дата:** июнь 2026  
**Статус:** закрыто для MVP EDT + XML

## Покрытые пути

| Формат | Метаданные формы | BSL модуль формы |
|--------|------------------|------------------|
| XML-выгрузка | `…/Forms/<Имя>/<Имя>.xml` | `FormModule.bsl`, `Ext/Form/Module.bsl` |
| EDT | `…/Forms/<Имя>/Form.form` | `Module.bsl` в каталоге формы |
| EDT CommonForms | `CommonForms/<Имя>/Form.form` | `Module.bsl` |

## Поведение `include_forms`

- **`false` (по умолчанию):** всё под `Forms/` и `CommonForms/` (`.bsl`, `.form`, `.mdo`) исключается из сканирования.
- **`true`:** индексируются `Form.form`, XML форм, BSL-модули форм (`Module.bsl`, `FormModule.bsl` и др. из `BSL_MODULE_NAMES`).
- Для EDT объектные `.mdo` внутри `Forms/` не дублируются — пропускаются при полном скане `.mdo`.

## Исключения (шум)

- XML: `Help.xml`, `Picture.xml`, `Predefined.xml` — не считаются метаданными формы.
- Глобы `**/Templates/**`, бинарники — по-прежнему исключены.

## Ограничения (известные)

1. **Managed form UI** (элементы формы в `.form`) — в чанк попадает усечённый XML (`raw_xml_summary`), без отдельного парсинга элементов UI.
2. **Вложенные формы / табличные формы** — не выделены отдельным типом; идут как `Form` с родителем в `comment`.
3. **EDT без `src/`** — если `.mdo` лежат в корне репозитория, `detect_format` всё равно определит EDT, но рекомендуется стандартная структура `src/`.

## Рекомендации

- Для конфигураций с тяжёлыми формами включайте `include_forms: true` и планируйте полную переиндексацию при смене флага.
- Сравнение веток: BSL diff форм виден в `compare_profiles` → `bsl.changed`.

## Тесты

`tests/test_include_forms.py` — XML и EDT fixtures (off/on, extract, wizard preview).
