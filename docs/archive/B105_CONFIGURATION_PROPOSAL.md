# B10.5f — Configuration architecture proposal (STOP-GATE)

**Предложение, не реализация.** Новый resolver, `formatter_profiles.toml`, новые CLI-флаги и миграция параметров не созданы. Решение необходимо согласовать отдельно.

## Сравнение вариантов

| Вариант | Один источник | Профили/типизация | SQLFluff и риски | Вывод |
|---|---|---|---|---|
| A. Только .sqlfluff | Не для Python/layout без собственного namespace | Потребуется собственная схема поверх INI и профильное наследование | Нельзя считать layout rules активными в нашем renderer; permissive config даёт ложные ожидания | Не рекомендован |
| B. Только TOML, без адаптера | Да для Python | Удобно | FluffConfig не читает произвольный formatter_profiles.toml напрямую; SQLFluff всё равно требует mapping | Неполное решение |
| C. TOML + программный адаптер к SQLFluff | Да, каждое поле определяется один раз | Явные defaults/overrides и строгая схема | FluffConfig(configs=..., overrides=...) подтверждён установленным 4.4.0; потребуется полная фиксация технических overrides | **Рекомендован после согласования** |
| D. TOML + технический .sqlfluff | Возможно при запрете повторяющихся ключей | Аналогично C | Два файла и правила проверки пересечений усложняют установку; риск случайного дублирования case/indent | Допустим, но лишний источник для текущего малого набора |

Дополнительно выявлен process cache файлов конфигурации в SQLFluff 4.4.0: новый FluffConfig.from_path не является гарантией hot reload. В C собственный неизменяемый snapshot и mapping устраняют неявное ожидание перезагрузки; точную reload policy определить явно.

SQLFluff умеет читать собственную структуру tool.sqlfluff в pyproject.toml; это не означает чтение произвольной профильной схемы. Вариант C использует обычный Python mapping в FluffConfig и не вызывает поиск файлов. Проверен API установленной библиотеки, зависимости не обновлялись.

## Предлагаемые файлы

- `formatter_profiles.toml`: только schema_version, default_profile, defaults и profiles; пользовательские параметры с реально реализованными consumers.
- `formatter_modules/formatter_config.py`: immutable dataclasses, загрузка абсолютного пути относительно модуля, проверка схемы, profile resolution и effective representation без SQL.
- `formatter_modules/sqlfluff_config_adapter.py`: перевод effective settings в отдельные parser/CP FluffConfig; технические invariants заданы кодом, не доступны в TOML.
- Тесты resolver/schema/profile isolation и byte-equivalence; старые golden не меняются.
- `.sqlfluff`: удалить из runtime только после доказанной миграции; не оставлять активную дублирующую конфигурацию. Если файл нужен для ручного sqlfluff CLI, генерировать его явно как производный артефакт с предупреждением, не поддерживать вручную второе значение.

## Предлагаемая схема первого этапа

Это иллюстрация будущего файла, **не установленная конфигурация**:

```toml
schema_version = 1
default_profile = "personal"

[defaults.layout]
indent_size = 4
select_comma_style = "leading"
group_by_comma_style = "leading"
order_by_comma_style = "leading"

[defaults.case]
keyword = "upper"
function = "upper"
identifier = "lower"
literal = "upper"
type = "upper"

[defaults.aliases]
table_as = "remove"
column_as = "preserve"

[profiles.personal]
[profiles.corporate]
```

Схема отражает только уже действующие правила. Сначала принимаются текущие значения как ограниченные enum; расширение диапазона разрешённых значений требует consumers и тестов, а не простого ослабления схемы. `indent_size` нельзя считать работающим до удаления всех Python +4 и передачи одного effective значения каждому renderer. CP policy нельзя менять до адаптации доказательства конкретных LintFix к resolved policy. В рамках B10.5 эти изменения не выполняются.

Max line length не включён в пользовательскую v1: нынешние 120 — технический параметр SQLFluff, не renderer. Будущий `layout.soft_line_limit=100`, CALL/function trailing, pack_to_width и preserve_valid_manual_breaks вводить вместе с B10.6 после согласования порогов. Нельзя выставить опцию, которая молча игнорируется. Параметры транспорта/журнала оставить отдельно от SQL-профиля; среда не должна переопределять SQL-style.

Дополнительные profile IDs можно предусмотреть в схеме как именованные overrides с ограниченным ASCII-идентификатором и обязательными personal/corporate. Resolver сможет разрешать только явно определённые ID; неизвестный ID — ошибка. Существующий DBeaver GUI продолжит показывать ровно 1/2. Доступ дополнительных профилей через headless CLI и будущие изменения UI согласуются отдельно; новая запись TOML не должна молча переназначать клавиши.

## Resolver и безопасность

1. Абсолютный путь к одному файлу относительно проекта; ни cwd, ни home, ни inline SQL directives, ни неявных пользовательских конфигов.
2. `schema_version` — int (bool не int для проверки), известная версия. Неизвестные ключи, профиль, тип, enum, duplicate TOML keys — явная ошибка. Defaults обязательны в согласованном составе.
3. Resolve: встроенные технические invariants → defaults → overrides выбранного профиля. Только известные leaf-поля; не разрешать произвольный passthrough в SQLFluff. Никаких циклических extends, источников из сети или переменных окружения в TOML.
4. Immutable effective settings с profile ID и fingerprint. Отдельная новая request boundary для каждого профиля. Не переносить кеши доказательств между разными effective settings.
5. Invariants: raw, Teradata/закреплённая грамматика, CP01–05 only, disable_noqa, strict validator, protected spans, atomic rollback, процедура-repeat, narrow prefix/table-AS evidence. Полей disable_validation и аналогов нет.
6. Ошибка конфигурации: CLI — краткая диагностика stderr и ненулевой код; DBeaver — исходные bytes, безопасный журнал, без текста в stdout/stderr. Никакого fallback на personal или defaults при неизвестном значении.
7. Ошибка чтения конфигурации не должна менять пользовательский файл. Конфигурация читается один раз на request, её snapshot относится ко всем фазам.
8. Эффективная конфигурация показывает источник каждого значения, profile ID, schema version и технические invariants. Без SQL, секретов и абсолютных пользовательских путей по умолчанию.

## CLI: предложение для согласования

Сохранить `python formatter.py [path]`. Добавить отдельный режим `python formatter.py --show-config --profile personal`, где stdout — JSON effective settings, SQL не читается. Нельзя смешивать show-config и форматирование одного файла; конфликт аргументов — ошибка. `--profile` для обычного headless форматирования также требует явного согласования интерфейса. DBeaver-команда остаётся ровно `dbeaver_adapter.py path`; профиль приходит из существующего Tk UI.

Python 3.11+ имеет tomllib. Сегодня зависимость SQLFluff допускает Python 3.10, а проект проверен на 3.12.8. До реализации решить: зафиксировать минимальную версию 3.11/целевую 3.12 либо разрешить tomli для 3.10. Новая зависимость сейчас не добавлена.

## План безопасной миграции

1. Согласовать схему/версии/настраиваемость и CLI.
2. Добавить resolver отдельно, пока runtime использует прежнюю конфигурацию. Test fixtures сравнивают effective defaults с текущим dump.
3. Подключить один effective snapshot через existing entry points без изменения public format_sql; передавать профиль из adapter, CLI сохраняет прежний default.
4. Перевести CP и Python consumers по одному семейству параметров, каждый раз сравнивать baseline output/diagnostics/двойной проход. Технические правила validator не становятся профилем.
5. Убрать чтение .sqlfluff из runtime только при полной эквивалентности. Проверить чужие cwd/home configs, оба профиля, исключения и потоковую изоляцию.
6. После приёмки конфигурации — отдельное согласование golden и thresholds B10.6. Ни одна из новых layout-возможностей не включается как побочный эффект миграции.

## Требуется решение пользователя

- Вариант C или D; рекомендуется C.
- Python минимум 3.11 (предпочтительно целевая 3.12) либо отдельное согласование tomli.
- Подтвердить `column_as=preserve`, единый `function` case без неподтверждённого различения built-in/UDF.
- Утвердить режим show-config и правила конфликтующих CLI-аргументов.
- Какие реально работающие style-поля разрешать изменять в первой версии; сначала фиксированные текущие значения безопаснее неподдержанных обещаний.

**STOP:** реализация нового конфигурационного слоя и B10.6/B11 не начата.
