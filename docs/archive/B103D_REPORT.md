# B10.3d — Test Suite Architecture & Cleanup

## Результат и границы

База: `df60328e249460313c4384d2b8c270039bbf746a` (`refactor/b10-3c-architecture`). Работа: `refactor/b10-3d-test-suite`.

**358 → 335 тестов; 0 FAIL / 0 ERROR до и после.** Удалены 23 доказанных повторных метода. Три уникальных входа исторического comment helper сохранены через публичный API. Все 73 SQL-примера B10.3c совпали побайтно на первом и повторном проходах; последовательности диагностических кодов также совпали. Строгая валидация выполнена для каждого результата.

Единственное изменение вне tests/docs — удаление `formatter_modules/formatter_comment_lists_preserve_layout.py`. Все остальные production Python-файлы совпадают побайтно с базой. `.sqlfluff`, зависимости, normative FORMATTER_CONTRACT и Windows setup не менялись. Commit, merge, push и deployment не выполнялись.

## Инвентаризация до изменений

Сначала зафиксированы исходные 30 модулей, 358 IDs, AST-хеши тел методов, fixtures, локальные helpers, imports/calls/assertions и полный baseline. Снимок Git-базы использовался для независимых прогонов. Корпоративный SQL не читался и не использовался.

Полная карта: [B103D_INVENTORY.json](B103D_INVENTORY.json). Для каждого модуля там перечислены зависимости от внутренних функций, fixtures, локальные fake AST и все исходные методы, включая negative cases. Время в таблице — приблизительное последовательное wall-time модуля, не CPU-профиль.

| Исходный модуль | Методов | Назначение/контракт | Новое место | До, с |
|---|---:|---|---|---:|
| `contract/test_contract_b102.py` | 11 | Процедурный layout, вложенность, строгая валидация и полный откат | `contract.test_procedure_layout` | 16.26 |
| `contract/test_contract_b102_transport.py` | 10 | Процедуры через CLI/adapter/profiles, BOM/CR, E001–E004, границы областей | `contract.test_procedure_transport` | 22.73 |
| `contract/test_contract_b103_diagnostics.py` | 6 | Opt-in trace, приватность, no stdout, parser-матрица, успешный multiline IN | `contract.test_diagnostics` | 34.18 |
| `contract/test_contract_b103b_indentation.py` | 7 | B10.3b: локальные отступы DML, несколько INSERT, IN/NOT IN, вложенные блоки | `regression.test_procedure_dml_indentation` | 36.13 |
| `contract/test_contract_b6.py` | 3 | Конфигурация вне cwd/home; transport без преждевременной нормализации байтов | `contract.test_source_transport` | 30.71 |
| `contract/test_contract_b7.py` | 13 | Fail-safe adapter: исключения, кодировки, logging, merged stdout/stderr | `contract.test_adapter` | 22.70 |
| `contract/test_contract_b9.py` | 9 | Оба профиля, GUI cancellation/errors, CLI без GUI | `contract.test_adapter_profiles` | 8.12 |
| `contract/test_contract_edge_v1_2.py` | 7 | Edge golden, import side effects, CLI/C001 и смешанные AND/OR | `contract.test_edge_cases_and_cli` | 15.54 |
| `contract/test_contract_golden.py` | 1 | Точный SQL-output и идемпотентность | `contract.test_contract_golden` | 12.85 |
| `contract/test_contract_golden_v1_2.py` | 3 | Тот же golden + уникальные проверки final newline/operators | `contract.test_contract_golden` | 14.92 |
| `regression/test_formatter.py` | 159 | Базовые клаузы, B2–B5 guards, scoped validator, CTE/sets/OVER/QUALIFY | `regression.test_clause_interactions`, `regression.test_commented_lists`, `regression.test_cte_layout`, `regression.test_edit_safety`, `regression.test_group_order_layout`, `regression.test_having_layout`, `regression.test_join_layout`, `regression.test_layout_regressions`, `regression.test_qualify`, `regression.test_select_layout`, `regression.test_set_operations`, `regression.test_validator_scopes`, `regression.test_where_layout`, `regression.test_windows` | 378.33 |
| `regression/test_formatter_b6.py` | 6 | Protected content/CRLF/CR, строгие отрицательные проверки, BOM/диагностика | `regression.test_source_preservation` | 12.15 |
| `regression/test_formatter_b8.py` | 9 | CP01–CP05, exact direction, неоднозначный AST, conflict/adapter refusal | `contract.test_case_normalization` | 6.91 |
| `regression/test_formatter_groupby_header.py` | 7 | Копия общих регрессий; nested GROUP BY header comment | `regression.test_layout_regressions` | 15.04 |
| `regression/test_formatter_spacing_fix.py` | 9 | Копия общих регрессий и секционных пробелов | `regression.test_layout_regressions` | 14.59 |
| `regression/test_formatter_stage9.py` | 6 | Копия общих регрессий комментариев, literals, idempotence | `regression.test_layout_regressions` | 13.81 |
| `regression/test_select_indent.py` | 2 | Ведущие запятые и nested SELECT; самостоятельные inputs | `regression.test_select_indent` | 2.35 |
| `unit/test_b102_integration.py` | 3 | Runtime/case grammar selection, SourceMap, самостоятельный DML | `contract.test_procedure_runtime` | 5.58 |
| `unit/test_formatter_clause_gaps.py` | 8 | Точечные clause edits, одиночные/множественные элементы, comments/JOIN отказ | `unit.test_formatter_clause_gaps` | 0.00 |
| `unit/test_formatter_comment_lists.py` | 3 | Исторический preserve-layout helper; 3 уникальных comment inputs | `regression.test_comment_attachment` | 0.00 |
| `unit/test_formatter_comment_lists_v2.py` | 4 | Канонический helper: inline comments, literal comma, ambiguous gap | `unit.test_inline_comment_lists` | 0.00 |
| `unit/test_formatter_comment_lists_v3.py` | 4 | Канонический helper: standalone/chain/header comments, ambiguous gap | `unit.test_standalone_comment_lists` | 0.00 |
| `unit/test_formatter_edits.py` | 14 | Planner: пересечения, одинаковые позиции, protected spans, атомарные группы | `unit.test_formatter_edits` | 0.00 |
| `unit/test_formatter_guarded_pass.py` | 6 | Сохранность токенов при охраняемом проходе и откат | `unit.test_formatter_guarded_pass` | 0.00 |
| `unit/test_formatter_list_gaps.py` | 5 | AST list gap edits, expression commas и защитные отказы | `unit.test_formatter_list_gaps` | 0.00 |
| `unit/test_formatter_lists.py` | 6 | Legacy simple-list API; реальные отдельные гарантии helper | `unit.test_formatter_lists` | 0.00 |
| `unit/test_formatter_protection.py` | 7 | Точные protected ranges, escapes, comments, quoted identifiers | `unit.test_formatter_protection` | 0.00 |
| `unit/test_formatter_runtime.py` | 9 | Карта смещений, round-trip, invalid bounds, конфигурация и line numbers | `unit.test_formatter_runtime` | 0.04 |
| `unit/test_procedure_prototype.py` | 17 | Явная процедурная грамматика, negative parser, границы листьев; 2 DML-регрессии | `regression.test_dml_idempotence`, `unit.test_procedure_grammar` | 23.15 |
| `unit/test_profile_selector.py` | 4 | Fake Tk: клавиши/мышь/focus/cancel/errors без графического окружения | `unit.test_profile_selector` | 0.00 |

Дополнительно: `tests/adapter_runner.py` перенесён в `tests/helpers/runners.py` без изменения команды subprocess. `tests/manual/input.sql` не изменён; добавлен ручной checklist, который ссылается на действующую Windows-инструкцию.

## Структура и fixtures

```text
tests/
  helpers/
    assertions.py   # точное сравнение protected regions
    fixtures.py     # SYNTHETIC, SIMPLE_INPUT/EXPECTED, wrap/walk, fake clause
    runners.py      # headless adapter command
  fixtures/
    golden.py       # единая неизменённая копия двух одинаковых GOLDEN
    edge_cases.py   # отдельный набор edge GOLDEN
  unit/             # planner, protection, source-map, lists, grammar, fake Tk
  contract/         # public output/transport/case/profiles/diagnostics
  regression/       # SQL-семейства и ранее найденные дефекты
  manual/           # Windows/DBeaver checklist, исходный input.sql
  README.md
```

Монолит из 1896 строк разделён по существующим классам поведения, без переписывания методов. Historical B-классы оставлены как provenance; имена модулей теперь описывают предмет проверки. Два вводящих в заблуждение имени DML-тестов (`non_idempotence`, `protected_refusal`) заменены именами успешного поведения. Старый тест перемещения запятой получил имя, явно описывающее сохранение привязки комментария.

Тесты больше не импортируют другие test-модули для доступа к данным. GOLDEN и процедурные строки перенесены дословно. Различные локальные fake Segment не объединены в универсальный AST: их поля и контекст отличаются. Не введены кэшированные mutable linters, runner-фреймворк или новые зависимости. Не созданы неиспользуемые каталоги sql/expected: существующие Python fixtures действительно используются в нескольких проверках.

Общий assertion сравнивает **тип, число, порядок и точное содержимое** protected spans. Повторные проходы остаются явно в тестах: там различаются диагностические и транспортные гарантии. CLI subprocess не объединён с adapter subprocess: кодировки, env и поведение stderr различаются.

## Доказательство дедупликации

| Удалённое повторение | Методов | Сохранённая проверка | Основание |
|---|---:|---|---|
| `test_formatter_groupby_header.FormatterTests` | 7 | `regression.test_layout_regressions.FormatterTests` | CASES, AST всех методов, imports, публичные вызовы и plain unittest context одинаковы |
| `test_formatter_spacing_fix.FormatterTests` | 9 | тот же класс | То же; оба дополнительных spacing-метода уже присутствовали в базовом классе |
| `test_formatter_stage9.FormatterTests` | 6 | тот же класс | То же; включая multiline literal, validator rejection и comments |
| `test_contract_golden_v1_2.test_exact_output_and_idempotence` | 1 | `test_contract_golden.ContractGoldenTests` | Одинаковые GOLDEN, вызовы format_sql, assertions, отсутствие специальных setup/diagnostic paths |

Две уникальные проверки operators/final newline из v1.2 перенесены в сохранённый golden-класс. Не удалены похожие методы разных классов с разными `CASES`: внешне одинаковое тело цикла не доказывает эквивалентность входов.

[Полная карта 358 старых IDs → 335 новых IDs](B103D_TEST_MAP.json) содержит причину каждого переноса/объединения. Проверка AST тел методов после нормализации **только путей fixture imports и названий методов** показала отличия ровно у трёх заменённых historical-helper проверок. Остальные assertions и значения fixtures сохранены. Два вспомогательных procedural `check()` используют эквивалентный общий protected assertion; количество проходов сохранено.

## Аудит исторического comment helper

Поиск всех Python-ссылок установил один consumer: старый `tests/unit/test_formatter_comment_lists.py`. Runtime импортирует канонический `formatter_comment_lists.py`; старый helper не экспортируется как публичный API. Контракт § сохранности и § комментариев разрешает менять внешний отступ при доказанной привязке, сохраняет trailing comment у предыдущего элемента и требует консервативности для неоднозначного gap.

| Точный исходный input (экранированный) | Исторический helper | Публичный runtime / сохранённая гарантия |
|---|---|---|
| `SELECT a\n-- explanation\n, b` | Не отступал comment/comma | `SELECT\n    a\n    -- explanation\n    , b\n`; standalone comment перед b |
| `SELECT a -- explanation\n, b` | Возвращал None | `SELECT a -- explanation\n    , b\n`; trailing comment остаётся у a |
| `SELECT a, -- explanation\nb` | Возвращал None | `SELECT\n    a -- explanation\n    , b\n`; comma переносится, comment остаётся у a |

Старые None означали ограничение частного helper, а не публичное требование отказа. Противоречия действующему контракту не выявлено. Перед удалением все три входа проверены на неизменённом runtime. Новые regression-тесты сохраняют сами входы и проверяют attachment anchors, ровно один comment, точные protected bytes, strict validator, отсутствие диагностик и второй проход. Это смена уровня проверяемого контракта после аудита, **не замена expected ради зелёного прогона**. Канонические unit-тесты отдельно сохраняют exact output, planner/protection и отказ на ambiguous gap. Сохранение `SELECT a` на первой строке второго примера не объявлено новым стилевым правилом: этот regression проверяет attachment; общая полная канонизация произвольных LF-раскладок остаётся существующим ограничением контракта. Ссылок на удалённый модуль в исполняемом коде не осталось.

## Сохранённые гарантии и negative cases

- E001: planner intersections/same-position inserts и процедура с инъекцией конфликтов.
- E002: protected-span rejection, атомарная группа, CP conflict и procedural transport rollback.
- E003: non-idempotent injected nested layout и недостаточный procedural margin. Успешный multiline IN из B10.3b не заменён проверкой отказа.
- E004: named windows через formatter/CLI/adapter и исходные bytes при отказе.
- C001: ambiguous comment ownership, CLI stderr, adapter logging и полный procedural rollback.
- CP01–CP05: только доказанные изменения, negative token/direction/protected/Unicode cases; нет общего casefold-допуска.
- LF/CRLF/CR/mixed, BOM, multiline comments/literals/quoted identifiers, source-map round-trip и точные границы edits — отдельные исходные проверки сохранены.
- WHERE/HAVING/QUALIFY scopes, nested SELECT, CTE, sets, OVER, IN/NOT IN и процедурные DML/block/loop boundaries сохранены.
- Personal/Corporate, cancellation, GUI failure, formatter exceptions, inaccessible log, merged stderr/stdout, arbitrary cwd и foreign configuration сохранены.
- CLI остаётся headless, GUI unit-тестируется через fake Tk. Реальная Windows/VDI и DBeaver этим этапом не подтверждены.

## 73 примера B10.3c

Корпус извлечён из frozen baseline до переноса fixtures: оба golden-набора, edge GOLDEN, четыре исторических CASES-набора и три процедурных примера. Все 73 provenance-ключа сохранены, даже когда SQL повторяется. Эталон — зафиксированные B10.3c first/repeat outputs, проверенные по архивному `B103C_OUTPUT_CHECK.json`. После переноса все входы выполнены через актуальный format_sql, затем повторно; вызван strict validator.

Результат: **73/73** первых SQL-output, **73/73** повторных SQL-output, **73/73** пар последовательностей diagnostic codes совпали. [Хеши входов/результатов и коды](B103D_OUTPUT_CHECK.json). Golden SQL не редактировался.

## Запуски и время

Среда: локальная macOS, Python 3.12.8, SQLFluff 4.4.0. Использован `/tmp/sql_formatter_b103_venv/bin/python`, `PYTHONDONTWRITEBYTECODE=1`. Команда каждого полного прогона:

```sh
python -m unittest discover -s tests -t . -p 'test_*.py' -v
```

Первый полный baseline: **358/0/0, 642.395 с**. Отдельный последовательный baseline с внешним сбором времени: **358/0/0, 686.202 с wall time**. После: **335/0/0, 749.644 с wall time**. В этом замере длительность **выросла на 63,4 с (+9,2%)**; ускорение не подтверждено. Это один локальный замер на вариант, не статистический benchmark и не Windows-оценка. Убраны повторные вызовы parse/format/repeat, но это не дало измеренного ускорения. Причина роста wall time не установлена; порядок тестов изменился, а нагрузка и состояние машины не контролировались. Для вывода о скорости нужны чередующиеся повторные замеры в одинаковых условиях. Production runtime здесь не менялся.

Сборщик лишь читает вывод штатного unittest subprocess; не подменяет runner, TestCase, runtime или SQLFluff. Модульные интервалы приблизительны: startup/warnings могут сдвигать границы. Прогоны выполнялись **последовательно**. [Полные измерения и IDs](B103D_TIMINGS.json).

| Новый модуль | Методов | После, с |
|---|---:|---:|
| `tests.contract.test_adapter` | 13 | 40.00 |
| `tests.contract.test_adapter_profiles` | 9 | 9.86 |
| `tests.contract.test_case_normalization` | 9 | 7.66 |
| `tests.contract.test_contract_golden` | 3 | 14.63 |
| `tests.contract.test_diagnostics` | 6 | 56.02 |
| `tests.contract.test_edge_cases_and_cli` | 7 | 14.64 |
| `tests.contract.test_procedure_layout` | 11 | 24.68 |
| `tests.contract.test_procedure_runtime` | 3 | 6.17 |
| `tests.contract.test_procedure_transport` | 10 | 37.28 |
| `tests.contract.test_source_transport` | 3 | 48.92 |
| `tests.regression.test_clause_interactions` | 4 | 28.35 |
| `tests.regression.test_comment_attachment` | 3 | 1.41 |
| `tests.regression.test_commented_lists` | 10 | 34.47 |
| `tests.regression.test_cte_layout` | 11 | 15.48 |
| `tests.regression.test_dml_idempotence` | 2 | 1.78 |
| `tests.regression.test_edit_safety` | 6 | 10.83 |
| `tests.regression.test_group_order_layout` | 10 | 39.40 |
| `tests.regression.test_having_layout` | 7 | 29.31 |
| `tests.regression.test_join_layout` | 10 | 28.21 |
| `tests.regression.test_layout_regressions` | 9 | 15.10 |
| `tests.regression.test_procedure_dml_indentation` | 7 | 61.89 |
| `tests.regression.test_qualify` | 19 | 36.26 |
| `tests.regression.test_select_indent` | 2 | 2.60 |
| `tests.regression.test_select_layout` | 17 | 57.34 |
| `tests.regression.test_set_operations` | 18 | 28.43 |
| `tests.regression.test_source_preservation` | 6 | 11.91 |
| `tests.regression.test_validator_scopes` | 10 | 7.63 |
| `tests.regression.test_where_layout` | 8 | 33.06 |
| `tests.regression.test_windows` | 20 | 25.17 |
| `tests.unit.test_formatter_clause_gaps` | 8 | 0.00 |
| `tests.unit.test_formatter_edits` | 14 | 0.00 |
| `tests.unit.test_formatter_guarded_pass` | 6 | 0.00 |
| `tests.unit.test_formatter_list_gaps` | 5 | 0.00 |
| `tests.unit.test_formatter_lists` | 6 | 0.00 |
| `tests.unit.test_formatter_protection` | 7 | 0.00 |
| `tests.unit.test_formatter_runtime` | 9 | 0.04 |
| `tests.unit.test_inline_comment_lists` | 4 | 0.00 |
| `tests.unit.test_procedure_grammar` | 15 | 21.03 |
| `tests.unit.test_profile_selector` | 4 | 0.00 |
| `tests.unit.test_standalone_comment_lists` | 4 | 0.00 |

Самые дорогие модули: `tests.regression.test_procedure_dml_indentation` (61.9 с), `tests.regression.test_select_layout` (57.3 с), `tests.contract.test_diagnostics` (56.0 с), `tests.contract.test_source_transport` (48.9 с), `tests.contract.test_adapter` (40.0 с). Основная стоимость — настоящие parse/layout/CP/strict validation и повторное форматирование, плюс отдельные subprocess. Эти операции не отключались и не кэшировались. Профиль production по внутренним фазам здесь не снимался; утверждений о стоимости конкретного внутреннего вызова этот замер не делает.

## Финальные проверки и оставшийся долг

- Полный unittest, imports/discovery, mapping completeness, сравнение fixture values и SQL outputs — PASS.
- `git diff --check` — PASS; status проверен, изменения ограничены тестами/docs и удалением доказанно неиспользуемого helper.
- В корне docs ровно три активных документа; historical reports не переписаны. Добавлены только B103D audit artifacts.
- Private SQL и diagnostic logs не добавлены. Новые данные получены только из существующих synthetic fixtures; файлы пользователя не читались.
- Сохранены исторические B-class IDs и часть локальных assertions для provenance. Дальнейшая косметическая унификация не нужна для безопасности.
- Некоторые focused regression loops повторно выбирают golden cases: сохранены намеренно, поскольку они привязаны к дополнительным гарантиям/diagnostics. Здесь устранены только доказанные полные дубли.
- Дорогие интеграционные проверки остаются; production performance, JOIN derived-table layout, произвольные LF-переносы, DDL и Windows-функциональность не менялись.

**Этап остановлен для ревью. Коммит не создан.**
