# B10.3c — Architecture Cleanup & Documentation Consolidation

## База и границы

Baseline B10.3b: `96592342e42721607db1204142e47bd829e8a024`, исходная ветка `feature/b10-stored-procedures`, `git status --short` перед работой пуст. B10.3b уже был сохранён пользователем отдельным коммитом; повторный коммит не создавался. Создана `refactor/b10-3c-architecture`.

Baseline тестов и SQL-output снят с отдельной неизменяемой копии `git archive HEAD` в `/tmp/b103c-baseline`, до структурных изменений. Корпоративный SQL не использовался. Изменения formatter_procedure.py B10.3b, карта смещений, planner, protected spans, валидатор, CP01–CP05 и `.sqlfluff` не редактировались.

## Перемещения и удаления

| Old | New | Причина / доказательство |
|---|---|---|
| `dbeaver_profile_selector.py` | `formatter_modules/profile_selector.py` | Внутренний UI, не точка входа. Файл побайтно идентичен; импорты и test patches обновлены. |
| `prototypes/teradata_procedures.py` | `formatter_modules/teradata_procedure_grammar.py` | Действующая production-грамматика. AST всех классов идентичен исходному; правила не менялись. |
| `prototype_config()` | `procedure_config()` | Внутренний конструктор грамматики; все вызовы в selector/tests обновлены. `parse_procedure()` сохранён как отдельный LF-only helper. |
| `teradata_procedure_prototype` | `teradata_procedure` | Имя частного Dialect, без регистрации в глобальном registry; SQL/сегменты не меняются. |
| `formatter_comment_lists_v3.py` | `formatter_comment_lists.py` | Единственный прежний production-путь (`formatter.py` импортировал v3). Реализация перенесена побайтно. |
| Прежний `formatter_comment_lists.py` | `formatter_comment_lists_preserve_layout.py` | Отдельный исторический helper-контракт сохраняет отступы standalone comments. Три прежних теста требуют отличающегося SQL-output; helper сохранён без изменения алгоритма, только docstring уточнён. Движок его не импортирует. |
| `formatter_comment_lists_v2.py` | Удалён, четыре теста используют канонический helper | Поиск импортов выявил только unit-тесты, production его не использовал. Все требуемые ими inline-comment случаи покрываются каноническим алгоритмом с прежним точным SQL-output. |
| `dbeaver_formatter.py` | Удалён; поддержанные точки — adapter и CLI formatter.py | Полный файл — чтение bytes, decode, вызов format_sql, UTF-8 stdout и простой stderr/exit handling. Уникальных правил SQL нет. Официальная документация B7 уже запрещала подключать его к DBeaver из-за merged stderr; все репозиторные вызовы найдены в тестах/истории и обновлены. |
| `prototypes/__init__.py`, каталог `prototypes/` | Удалены | После переноса единственного модуля необходимого кода не осталось; production/test imports из prototypes отсутствуют. |
| `SourceLinter._linter` | Удалено неиспользуемое поле | Поиск всех Python-файлов: единственная ссылка — присваивание в __init__. parse_string создаёт фактически используемый Linter с выбранным config; он сохранён. |
| `formatter.DIALECT` | Удалена неиспользуемая константа | Поиск Python-файлов: только определение, ни одного чтения. Реальная конфигурация задаётся в runtime/dialect. |

Удаление старого CLI — явно разрешённое упразднение точки входа, не изменение команды официального адаптера. Нельзя подтвердить отсутствие неизвестных внешних скриптов за пределами репозитория: такие установки должны перейти на formatter.py (headless) либо официальный adapter согласно задаче. Старый обработчик stderr не переносился в безопасный адаптер, поскольку он там недопустим.

## Разделение ответственности

- `formatter.py`: библиотечные `format_sql`/validator, основной pipeline и существующий headless CLI. Большой декомпозиции не было.
- `dbeaver_adapter.py`: файловый запуск, bytes-транспорт, выбор/маршрутизация и fail-safe. Его единственное изменение — путь ленивого импорта селектора. Аргументы, exit codes, stderr-silencing, журналы, отмена и диагностика сохранены.
- `formatter_modules/profile_selector.py`: только UI-выбор, без форматирования.
- `PROFILE_FORMATTERS`: существующая таблица bytes-маршрутов оставлена для совместимости. Оба ID используют один format_bytes, который вызывает общий движок. Настройки общие в `.sqlfluff`; отдельная система профилей/registry/дубли движка не нужны.
- `formatter_runtime.py`: проектный config и SourceMap. `formatter_case.py` имеет намеренно отличный CP-only config; объединение загрузчиков не выполнялось.
- `diagnose_formatter.py`: отдельный headless-инструмент без SQL-вывода, интерфейс не менялся.

Список production-импортов до/после: [B103C_IMPORTS.json](B103C_IMPORTS.json). Статический граф всех внутренних imports (включая ленивые) ацикличен. Неиспользуемых импортированных имён по AST-проверке production не найдено. Активных TODO/FIXME в Python-модулях нет. В _indent_comment_chain сохранено историческое избыточное вычисление desired для последнего комментария, сразу заменяемое следующей веткой: ради побайтного переноса канонического алгоритма оно не переписывалось. Единственная внешняя прямая зависимость — SQLFluff; она используется, requirements не изменён.

Проверены исторические функции: например, remove_formatter_where_prefix используется regression-тестами, normalize_groupby_header_comments и format_nested_join вызываются движком. Они не удалялись. Остальные legacy layout-проходы работают через guarded_pass; их преобразование/объединение вне B10.3c. Версионные имена оставлены только у тестов, предназначенных для B10.3d.

## Адаптация тестов без изменения SQL-ожиданий

Каталоги tests и fixtures не переносились. Импорты grammar/selector/comment helper и строки patch обновлены. В двух тестах точек входа уточнены имена методов: B6 проверяет точное чтение поддержанного CLI, B7 — его коды/каналы. Удалённый wrapper больше не запускается вторым вариантом тех же CLI-сценариев. Набор тестовых методов не сокращён.

Адресные переименования проверок точек входа:

| Old | New | Причина |
|---|---|---|
| B6 `test_dbeaver_reads_exact_bytes_before_formatter` | `test_cli_reads_exact_bytes_before_formatter` | Точное чтение поддержанного CLI после удаления старого wrapper; источник и bytes-ожидание те же. |
| B7 `test_legacy_cli_interface_unchanged` | `test_supported_cli_interface` | Проверяются текущий CLI и его существующий stderr/exit-code контракт. |

B6 дополнительно запускает официальный headless-адаптер через существующую test fixture при проверке cwd/конфига; проверки чтения bytes, SQL-output и диагностики сохранены. У поддержанного formatter.py ошибка разбора остаётся ValueError в stderr/exit 1; тест проверяет именно этот существующий интерфейс вместо удалённого сообщения `Formatting failed`. Это изменение проверки точки входа, не golden SQL. В in-process CLI-тесте поток flush-ится перед чтением буфера (обычный print использует TextIOWrapper). GUI-фокус/клавиши проверяются fake Tk, не реальной VDI.

## Документация и архив

В корне docs ровно ROADMAP.md, DBEAVER_WINDOWS_SETUP.md и FORMATTER_CONTRACT.md. README создан как краткая навигация/запуск/тестирование. Старые документы сохранены полностью, побайтное сравнение с baseline выполнено для всех 17 переносов, включая прежнюю Windows-инструкцию. Единственная внутренняя markdown-ссылка исторического отчёта B101 на AST-файл остаётся рабочей, поскольку оба перенесены вместе.

| Исторический файл | Архив |
|---|---|
| `docs/B101_REPORT.md` | `docs/archive/B101_REPORT.md` |
| `docs/B101_SYNTHETIC_AST.txt` | `docs/archive/B101_SYNTHETIC_AST.txt` |
| `docs/B102_REPORT.md` | `docs/archive/B102_REPORT.md` |
| `docs/B103A_REPORT.md` | `docs/archive/B103A_REPORT.md` |
| `docs/B103B_REPORT.md` | `docs/archive/B103B_REPORT.md` |
| `docs/B7_REPORT.md` | `docs/archive/B7_REPORT.md` |
| `docs/B8_REPORT.md` | `docs/archive/B8_REPORT.md` |
| `docs/B9_REPORT.md` | `docs/archive/B9_REPORT.md` |
| `docs/DBEAVER_WINDOWS_SETUP.md` | `docs/archive/DBEAVER_WINDOWS_SETUP_B10_3B.md` |
| `docs/SQL_formatter_roadmap.md` | `docs/archive/SQL_formatter_roadmap.md` |
| `docs/contract_bochenkov.md` | `docs/archive/contract_bochenkov.md` |
| `docs/stage9_test_results.txt` | `docs/archive/stage9_test_results.txt` |
| `docs/teradata_formatter_contract_v1.1.md` | `docs/archive/teradata_formatter_contract_v1.1.md` |
| `docs/teradata_formatter_contract_v1.md` | `docs/archive/teradata_formatter_contract_v1.md` |
| `docs/test_results.txt` | `docs/archive/test_results.txt` |
| `CODEX_TASK_SQL_FORMATTER.md` | `docs/archive/CODEX_TASK_SQL_FORMATTER.md` |
| `SQL_FORMATTER_AUDIT.md` | `docs/archive/SQL_FORMATTER_AUDIT.md` |

Архивные тексты описывают состояние своего этапа, поэтому исторические упоминания старых путей/команд в них не переписывались. Актуальные инструкции содержатся только в трёх документах корня docs.

## Итоговая структура

```text
.sqlfluff
README.md
dbeaver_adapter.py
diagnose_formatter.py
docs/
    ROADMAP.md
    DBEAVER_WINDOWS_SETUP.md
    FORMATTER_CONTRACT.md
    archive/  (история, B103C_REPORT.md и доказательства проверки)
formatter.py
formatter_modules/
    __init__.py
    formatter_case.py
    formatter_clause_gaps.py
    formatter_comment_lists.py
    formatter_comment_lists_preserve_layout.py
    formatter_dialect.py
    formatter_edits.py
    formatter_guarded_pass.py
    formatter_list_gaps.py
    formatter_lists.py
    formatter_procedure.py
    formatter_protection.py
    formatter_runtime.py
    formatter_trace.py
    profile_selector.py
    teradata_procedure_grammar.py
requirements.txt
sql_formatter.zip
tests/
    adapter_runner.py
    contract/
    regression/
    unit/
    manual/
```

## Риски и технический долг

- Ручная Windows/VDI приёмка не выполнена. Сохраняются риски фокуса Tk, quoting/timeout конкретного DBeaver, запретов запуска/доступа, оборванного stdout. При обновлении переносить весь пакет, не одиночные файлы; следить за `.sqlfluff`.
- Совместимость неизвестных внешних импортов старых внутренних путей не обещается. Официальная команда DBeaver неизменна.
- Compatibility-helper с отдельным старым SQL-output оставлен осознанно; его тесты и исторические имена требуют B10.3d, а не изменения ожиданий здесь.
- Процедурный private hook SQLFluff 4.4.0 сохранён. Конфиги parser/CP намеренно не объединялись. Большие повторные проверки и производительность — отдельная задача.
- JOIN с подзапросами, пробел перед алиасом, ON, первый верхнеуровневый отступ и произвольные LF-переносы записаны как Known issue, не исправлены этим этапом.
- DDL B11 и общая реорганизация тестов не начинались. Приватный SQL в этапе не использовался.

Никакого merge, push, deployment или коммита B10.3c: коммит допускается только после отдельного согласования.

## Проверки

Baseline, неизменяемая копия B10.3b: `python -m unittest discover -s /tmp/b103c-baseline/tests -t /tmp/b103c-baseline -p 'test_*.py' -v` — **358 tests, 0 FAIL, 0 ERROR**, 885.332 с. Целевой прогон перемещений: 40 тестов; первый прогон выявил только отсутствие flush в адаптированном in-process CLI-тесте. После добавления flush этот тест отдельно PASS; SQL-ожидание не менялось.

Снимки сняты по GOLDEN из трёх contract-модулей, CASES из четырёх regression-модулей и трём процедурным источникам SYNTHETIC/SIMPLE_INPUT/REPRO. Всего **73 именованных случая** (между историческими наборами есть дубликаты). Для каждого сохранён первый SQL-output, повторный output и коды диагностики обоих вызовов; выполнялась независимая validate_sql_unchanged. До и после все эти данные совпадают побайтно; все 73 повторных результата идентичны первым. Никаких ожидаемых SQL-строк в тестах не изменено. Хеши по случаям: [B103C_OUTPUT_CHECK.json](B103C_OUTPUT_CHECK.json).

Проверены внутренние markdown-ссылки файлов/якорей README и docs; ошибки отсутствуют. Архивные источники по SHA-256 побайтно совпадают с baseline. Ни production-импортов из prototypes, ни старых путей selector/comment-v2/v3 в Python нет. Внешние ссылки исторических документов сохраняются как ссылки на источники своего времени, их содержание не является текущим контрактом.

Перед рефакторингом файловые точки входа: formatter.py, dbeaver_adapter.py, dbeaver_formatter.py, diagnose_formatter.py. После: formatter.py, dbeaver_adapter.py, diagnose_formatter.py. Низкоуровневый parse_procedure остаётся функцией, не вторым адаптером. Полный список production imports до/после приложен выше.

## Окончательный результат

| Проверка | До | После |
|---|---:|---:|
| Полный unittest discover | 358 / 0 FAIL / 0 ERROR | 358 / 0 FAIL / 0 ERROR |
| Длительность | 885.332 с | 825.337 с |
| Именованные SQL-примеры | 73 | 73 побайтно идентичных |
| Идемпотентность примеров | 73/73 | 73/73 |
| Диагностические коды двух проходов | Сохранены в snapshot | Точно совпадают |

Финальная команда: `python -m unittest discover -s tests -t . -p 'test_*.py' -v`. Python 3.12.8 / SQLFluff 4.4.0; среды одинаковые, но нагрузка параллельных проверок различалась, поэтому длительности не служат доказательством ускорения. Все прежние 358 тестов сохранены по количеству, включая строгий validator, атомарность, CP01–CP05, B10.3b, оба профиля и диагностику.

Дополнительный установочный smoke-test: копия только актуальных файлов/пакета в каталоге с пробелами и кириллицей, другая cwd с посторонним `.sqlfluff`, синтетическая процедура с BOM/CRLF и многострочным IN. Personal/Corporate дают ожидаемый SQL, Cancel возвращает исходные байты, файл не изменён; объединённый stdout/stderr содержит только SQL. Headless diagnosis возвращает 0 без stdout/stderr. Это macOS subprocess-проверка, не Windows-приёмка.

`git diff --check` — PASS. Все локальные markdown-ссылки файлов и якорей проверены, корень docs содержит ровно три актуальных документа. Реорганизация тестов B10.3d не начата. Рабочие изменения B10.3c готовы к отдельному согласованию коммита в `refactor/b10-3c-architecture`.
