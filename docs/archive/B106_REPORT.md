# B10.6 — Configurable Lists, Unicode, Windows Integration

Дата: 11.11.2026. База: `74b3f2437eda6a673d329ff765fd6c801aa9e313`.
Ветка: `feature/b10-6-lists-unicode-windows` от чистой feature/b10-5f-user-profiles.
Новый Corporate-default не установлен. Main, merge и rebase не затрагиваются.

## Изменения

`parenthesized_lists.py` выбирает только bracketed-узлы после непосредственного
IN в expression либо строки values_clause. Подзапрос исключается по AST.
Прямые comma отделяют элементы, а вложенные функции/CAST/CASE остаются целыми.
Редактируются gaps вокруг элементов и разделителей, а не выражения. Каждая
группа имеет group_id и проходит неизменённый B2 planner/protected spans.
Неоднозначные комментарии дают C001 без частичного применения группы.

Публичная конфигурация: `[layout.parenthesized_lists]`, mode из трёх значений,
max_line_length integer 20–1000, default 100. Внутри immutable Settings хранится
нормализованный раздел parenthesized_lists. Отсутствие mode — внутренний None,
означающий прежний output, а не новое публичное значение TOML. Неиспользуемый
лимит нормализуется к 100, чтобы не открывать селектор из-за неэффективного отличия.
Шаблон содержит закомментированный пример, поэтому его копирование не меняет
Corporate. Ошибки новой секции используют прежний ConfigurationError/уведомления.

Adaptive учитывает реальный префикс/суффикс и внешний процедурный отступ через
узкий ContextVar, установленный только на вызов DML; он сбрасывается в finally.
При нескольких списках зависимые переносы проверяются до неподвижной точки,
не более числа списков + 3 проходов. Цикл/несходимость — исключение и штатный
атомарный fail-safe адаптера/процедуры. Отсутствие mode не добавляет AST-проходов.
Длинный целый элемент или текст вне списка может превышать soft limit.

## Unicode: причина и исправление

Штатный SQLFluff 4.4.0 использует ASCII `[0-9a-zA-Z_]+` в lexer word и ASCII
NakedIdentifierSegment. Кириллический алиас становился unlexable/unparsable.
`teradata_unicode.py` расширяет только project-local dialect, общий для runtime,
процедур и CP01–CP05. Использованы категории и дополнительные символы из
[Teradata Object Names](https://docs.teradata.com/r/Lake-Working-with-SQL/SQL-Reference/SQL-Fundamentals/Basic-SQL-Syntax/Object-Names).
Установленная библиотека и registry не изменяются. Для ASCII сохранена прежняя
ветвь grammar. Quoted identifiers обрабатываются прежними quote/protection rules.

CP02 не меняет Unicode-идентификаторы; Unicode function_name_identifier также
сохраняется при CP03. Смешанное имя с Unicode сохраняется целиком, включая ASCII
часть. Нет Unicode normalization, ASCII placeholders или общего разрешения
изменять токены. Строгий validator продолжает отвергать изменение написания/регистра.
Session charset, серверный NameValidationRule и разрешение имён по каталогу
по-прежнему не проверяются офлайн-форматтером.

Исходный пользовательский пример проверен локально из вложения в Corporate и
Personal: форматируется, alias сохраняется точно, strict validation и второй
проход PASS, диагностика пуста. Исходный SQL и имена объектов не перенесены в Git,
журнал или этот отчёт. Регрессионный тест использует синтетические таблицы.

Дополнительно проверены `İ`, `ı`, `K`, `Straße` и combining marks.
RegexParser использует IGNORECASE: локальный `(?-i:...)` в проверке non-ASCII
нужен, чтобы U+0130 не исчезал из этого класса из-за case matching.

Адресно обновлён `test_ambiguous_unicode_and_unparsable_fail_closed`: старый B8
ожидал отказа для `İ`. Теперь Unicode разрешён с сохранением исходных кодовых точек.
Добавлена строгая отрицательная проверка преобразования `İ` → `i` + combining dot.
Это обновление ожидания под явно заданную поддержку Unicode, не инфраструктурное
исправление. Golden-файлы, раскладка других старых ожиданий и validator не изменены.

## Один SQL в трёх режимах

Явный Personal, max_line_length=40; production default лимита — 100.

```sql
SELECT id FROM events WHERE status IN ('ACTIVE','BLOCKED','PENDING','SUSPENDED','CLOSED');
```
### single_line

```sql
SELECT
    id
FROM events

WHERE status IN ('ACTIVE', 'BLOCKED', 'PENDING', 'SUSPENDED', 'CLOSED')
;
```

### multiline

```sql
SELECT
    id
FROM events

WHERE status IN (
    'ACTIVE'
    , 'BLOCKED'
    , 'PENDING'
    , 'SUSPENDED'
    , 'CLOSED'
)
;
```

### adaptive

```sql
SELECT
    id
FROM events

WHERE status IN (
    'ACTIVE', 'BLOCKED', 'PENDING'
    , 'SUSPENDED', 'CLOSED'
)
;
```

## Windows / UTF-8 / DBeaver

CLI настраивал UTF-8 stdout, но не stderr. Теперь оба потока CLI явно UTF-8;
traceback не подавляется. Настройка происходит только в main, без import effects.
Автотест запускает subprocess с PYTHONIOENCODING=cp1251, декодирует stderr как UTF-8
и проверяет русское сообщение. При ошибке stdout пуст, исходный файл не меняется.
Это проверка байтов процесса, не доказательство реальной консоли PowerShell.

PowerShell 5.1 может декодировать/перекодировать native output, а `>`/Out-File
используют свои кодировки. Добавлены согласование Console.OutputEncoding,
PYTHONIOENCODING и вариант чтения UTF-8 diagnostic.jsonl через Get-Content -Encoding
UTF8. Основание: [Microsoft Character Encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1).
Диагностический файл уже использует ASCII-совместимый JSON с кодами, AST-типом,
строкой/позицией. Проблемный SQL-фрагмент намеренно не логируется: он может содержать
чувствительные имена и литералы. Контракт диагностики не расширен содержимым SQL.

DBeaver: External, Use temp file включён, timeout первоначально 10000 ms,
quoted python.exe/script/`${file}`. Без temp file входных байтов у адаптера нет,
поэтому гарантировать возврат SQL невозможно; неверная настройка явно запрещена
инструкцией. Поддерживаемый file→stdout контракт не менялся. При ошибке после чтения
адаптер возвращает исходные байты, включая BOM/CRLF и ошибочную кодировку, без stderr.
Ошибки до чтения и принудительное убийство процесса — прежние ограничения.

## Проверки

Команда в обеих средах: `<python> -m pytest tests -q`.

| Среда | Результат | Время полного прогона |
|---|---|---|
| Python 3.10.21 / SQLFluff 4.4.0 | 541 passed, 777 subtests passed, 0 FAIL / 0 ERROR | 426.88 s |
| Python 3.12.8 / SQLFluff 4.4.0 | 541 passed, 777 subtests passed, 0 FAIL / 0 ERROR | 410.87 s |

Baseline: 430 tests / 778 subtests; добавлено 111 тестов. Одно прежнее subtest
ожидание Unicode-отказа заменено прямыми positive/negative assertions в том же
B8-тесте, поэтому число subtests уменьшилось на один без удаления покрытия.
Времена получены при параллельных проверках, не являются сравнительным benchmark.

`tools/check_equivalence.py`: 73 historical + 43 B10.4 + 4 refusal cases полностью
совпадают с baseline; JSON после финального Unicode-исправления совпадает с
[B106_OUTPUT_CHECK.json](B106_OUTPUT_CHECK.json). Golden не менялись.
`git diff --check` — PASS. `uv pip check --python ...` — совместимость всех
установленных пакетов подтверждена в обеих средах (18 / 21 packages).
Аудит всех 21 изменённых/новых файлов: только согласованный объём; исходных
корпоративных имён из вложения, приватного SQL и секретов не обнаружено.

Матрица новых тестов: все три режима, короткие/длинные IN и NOT IN, многострочные
VALUES, NULL/CASE/CAST/functions, вложенные SELECT, CTE/процедуры, escaped literals,
trailing/standalone/block/mixed/ambiguous comments, LF/CRLF/CR protected spans,
полный префикс/суффикс и процедурный отступ, идемпотентность, строгая валидация.
Отдельно инъекции protected span и конфликтующей вставки подтверждают отказ всей
группы, а не части её edits. Unicode проверяется при lower/upper/preserve,
в quoted/unquoted identifiers, UDF, CTE и процедурах; invalid start/emoji дают отказ.
Transport: Unicode paths с пробелами, cwd вне проекта, legacy stream encoding,
байты отказа при объединении потоков, отмена и выбор Personal/Corporate.

## Рекомендация владельцу

Предлагается **adaptive, 100** как будущий Corporate-default: короткие списки
компактны, длинные читаются без разрыва значений. Это только предложение.
Текущий Corporate остаётся совместимым с базой; включение default требует отдельного
решения и оценки изменения golden/output. Multiline полезен для review списков,
single_line — для небольших фильтров и обмена SQL с внешними инструментами.

## Ручная приёмка и ограничения

1. На Windows Python 3.10/3.12 установить зависимости локально; проверить py -0p.
2. В DBeaver выставить External / Use temp file / UTF-8 / 10000 ms и quoted paths.
3. Без Personal проверить Unicode SELECT; повторный Ctrl+Shift+F не меняет SQL.
4. Скопировать шаблон в LOCALAPPDATA, раскомментировать новую секцию; проверить
   1 Personal, 2 Corporate, Esc, крестик и таймер. Сравнить три режима одного SQL.
5. Проверить кириллицу, CRLF внутри комментария/литерала, неверный SQL на копии,
   named window refusal, журнал и отсутствие диагностики в тексте редактора.
6. Проверить UNC исходники, локальный venv, права и реальный timeout большого SQL.

Windows/PowerShell 5.1/Tk focus/DBeaver/UNC/реальная Teradata в доступной среде не
запускались. CI/subprocess на macOS не заменяет эту приёмку. Не добавлялись EXE,
UI выбора режима, новые зависимости или скрытое чтение настроек DBeaver.
Несходимость раскладки не выдаёт частичный результат. Corporate fallback не
обещает новые режимы без явной настройки. Другие roadmap-направления не реализованы.

## Файлы и коммиты

- `README.md`
- `config_templates/personal.example.toml`
- `docs/DBEAVER_WINDOWS_SETUP.md`
- `docs/FORMATTER_CONTRACT.md`
- `docs/ROADMAP.md`
- `docs/USER_CONFIGURATION.md`
- `docs/archive/B106_OUTPUT_CHECK.json`
- `docs/archive/B106_REPORT.md`
- `formatter.py`
- `formatter_modules/formatter_case.py`
- `formatter_modules/formatter_config.py`
- `formatter_modules/formatter_dialect.py`
- `formatter_modules/formatter_procedure.py`
- `formatter_modules/parenthesized_lists.py`
- `formatter_modules/teradata_parameters.py`
- `formatter_modules/teradata_unicode.py`
- `tests/contract/test_b106_windows_transport.py`
- `tests/contract/test_case_normalization.py`
- `tests/manual/README.md`
- `tests/regression/test_parenthesized_lists.py`
- `tests/regression/test_unicode_identifiers.py`

Коммиты:

- `b5b8165d5882d490f2dd77dc405e8934cb0c9c24` — Unicode grammar/case и тесты.
- `2ba488be4c1f9cd5baf559ec2ab97c4f01c1b349` — Personal IN/VALUES и тесты.
- Финальный коммит `fix: make CLI diagnostics UTF-8 and document Windows integration` — transport-тесты, Windows/UTF-8, контракт и этот отчёт.
Итоговые SHA приведены в сообщении о завершении и истории этой feature-ветки.
