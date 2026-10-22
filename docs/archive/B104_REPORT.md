# B10.4 — SQL Layout Corrections

## Объём и baseline

Ветка `feature/b10-4-layout-fixes`, база B10.3d `79334d8b22b8d953750f4f32b5113389165c220d`: 335 tests, 0 FAIL, 0 ERROR. Реализованы четыре согласованных изменения: derived JOIN, пробел перед алиасом, корневой отступ, удаление необязательного табличного AS. ON остаётся на уровне JOIN; прежняя пустая строка перед JOIN сохранена. Иллюстративный отступ ON из задания не принят за новое правило: явное требование — сохранить существующее выравнивание.

Коммит, merge, push и deployment не выполнялись. Корпоративный SQL не использовался. Все примеры синтетические.

## Причины и реализация

| Дефект | Причина baseline | Изменение |
|---|---|---|
| Derived JOIN | `nested_query_gap_edits()` исключал JOIN с SELECT; fallback не оформлял тело, повтор добавлял пустую строку | Существующий рекурсивный AST renderer принимает прямые derived JOIN, рассчитывает уровни запросов, не применяет второй JOIN fallback к обработанной области |
| `)alias` | Не было edits промежутка derived table–alias | `table_alias_parts()` доказывает AST-форму; `table_alias_gap_edits()` заменяет только разрешённый промежуток одним пробелом |
| Начальный отступ INSERT/UPDATE и последующих операторов | Коррекция SELECT не охватывала корневые DML statement | `statement_margin_edits()` работает только с непосредственными statement корневого AST, удаляет их пробельный префикс; при соседнем операторе/комментарии на той же строке добавляет LF |
| Табличный AS | Старый контракт сохранял AS, validator запрещал удаление любого токена | Один атомарный edit промежутка таблица–алиас удаляет доказанный optional AS; validator разрешает только соответствующий исходный token index |

Точки реализации: `formatter_clause_gaps.py:240` (существующий renderer), `:885` (AST-witness алиаса), `:931` (корневая граница), `:952` (alias edits); `formatter.py:812` (снимок токенов), `:862` (validator), `:1083` (подготовительные edits).

В `formatter.py` эти локальные подготовительные edits проходят существующий planner и protected spans, затем SQL повторно разбирается для актуальных координат. `formatter_modules/formatter_clause_gaps.py` содержит AST-распознавание и изменения layout. Нет глобального regex, lstrip/dedent всего SQL, новых грамматических правил или копии движка. CP, source map, planner, procedural renderer и DBeaver adapter не изменены.

### Доказательство допустимости удаления AS

SQLFluff 4.4.0 `AliasExpressionSegment` допускает `AsAliasOperatorSegment` как optional. Применение дополнительно сужено: элемент FROM/JOIN состоит из table_expression и alias_expression; target — обычная table_reference либо bracketed query; alias — один naked/quoted identifier с необязательным одиночным AS. Alias column list, функция вместо таблицы, комментарий в промежутке исключают преобразование.

Валидатор использует тот же witness из **исходного** AST. Сохраняются типы, порядок и области токенов; добавлены области from_expression_element/alias_expression. Разрешена только потеря конкретного исходного AS. Его вставка, удаление column/CAST/CTE AS, изменение имени/ссылок, перестановка предиката, изменение JOIN, литералов или комментариев отклоняются. CP-изменения и WHERE/HAVING-префиксы продолжают проверяться отдельно. Protected spans сравниваются точно, без исключений.

## Воспроизведение до/после

Во всех примерах ниже actual B10.4 совпадает с ожидаемым контрактом; второй проход побайтно совпадает с первым. Диагностика обоих проходов пуста, независимая `validate_sql_unchanged(input, actual)` успешна. У derived JOIN baseline второй проход добавлял ещё одну пустую строку перед JOIN; у остальных baseline был стабильным, но нарушал новое требование.

### derived_join

Input:
```sql
SELECT a.id FROM t a LEFT JOIN (SELECT b.id FROM u b)cbm ON a.id=cbm.id;
```

Baseline actual:
```sql
SELECT
    a.id FROM t a 
LEFT JOIN (SELECT b.id FROM u b)cbm
ON a.id=cbm.id
;
```

B10.4 actual / expected:
```sql
SELECT
    a.id
FROM t a

LEFT JOIN (
    SELECT
        b.id
    FROM u b
) cbm
ON a.id = cbm.id
;
```

### derived_from

Input:
```sql
SELECT x FROM (SELECT x FROM t)q;
```

Baseline actual:
```sql
SELECT
    x
FROM (
    SELECT
        x
    FROM t
)q
;
```

B10.4 actual / expected:
```sql
SELECT
    x
FROM (
    SELECT
        x
    FROM t
) q
;
```

### leading_update

Input:
```sql
    UPDATE t SET a=1;
```

Baseline actual:
```sql
    UPDATE t SET a=1
;
```

B10.4 actual / expected:
```sql
UPDATE t SET a=1
;
```

### table_as

Input:
```sql
SELECT a.id AS x FROM t AS a JOIN u As b ON a.id=b.id;
```

Baseline actual:
```sql
SELECT
    a.id AS x
FROM t AS a

JOIN u AS b
ON a.id = b.id
;
```

B10.4 actual / expected:
```sql
SELECT
    a.id AS x
FROM t a

JOIN u b
ON a.id = b.id
;
```

### indented_insert

Input:
```sql
    INSERT INTO t SELECT a FROM u;
```

Baseline actual:
```sql
    INSERT INTO t
SELECT
    a
FROM u
;
```

B10.4 actual / expected:
```sql
INSERT INTO t
SELECT
    a
FROM u
;
```

## Обновлённые прежние проверки

Файлы golden fixtures не изменены. Следующие прежние проверки объявляли derived JOIN неподдержанным; их ожидания адресно приведены к требованию №1:

| Файл / тест | Прежде | Теперь |
|---|---|---|
| `test_clause_interactions.py`: `test_join_subqueries_remain_out_of_scope` → `test_derived_join_boundaries_are_owned_atomically` | Для двух derived JOIN нет edits/owners | Есть edits, owner `{0}`, единая группа |
| `test_cte_layout.py`: `test_future_constructs_and_join_subqueries_not_claimed` → `test_cte_derived_join_supported_other_feature_gates_preserved` | Derived JOIN в CTE исключён | Он поддержан; остальные проверки выключенных feature gates сохранены |
| `test_join_layout.py`: `test_join_subqueries_and_window_queries_not_claimed` → `test_derived_join_supported_windows_and_using_not_claimed` | Derived JOIN исключён | Поддержан; USING и выключенные окна по-прежнему исключены |
| `test_set_operations.py`: `test_future_constructs_not_claimed` → `test_derived_join_supported_other_feature_gates_preserved` | Derived JOIN в ветви UNION исключён | Поддержан; выключенные OVER/QUALIFY по-прежнему исключены |
| `test_commented_lists.py`: `test_query_group_integration_and_future_scope` | Derived JOIN с commented ORDER исключён | Поддержан; другие ограничения сохранены |

Единственное прежнее текстовое ожидание SQL изменено в `test_layout_regressions.py::test_groupby_header_comment_nested`:

```diff
- GROUP BY\n    1\n    , 2
+ GROUP BY\n        1\n        , 2
```

Причина: после корректного включения derived JOIN его SELECT/GROUP BY имеют уровень +4, а элементы GROUP BY — +8. Ранее fallback ошибочно оставлял элементы на +4. Это исправление вложенности по требованию №1, не новый стиль GROUP BY. Сохранены исходный SQL, проверка комментария и идемпотентности.

Первый промежуточный полный прогон обнаружил эти два устаревших ожидания (commented ORDER scope и nested GROUP BY indent); остальные проходили. Следующий полный прогон (358 тестов) обнаружил ещё одну старую отрицательную scope-проверку derived JOIN в ветви UNION. Она обновлена аналогично; отдельный целевой повтор — PASS (1 тест, 0.201 s). Production-код после этого не менялся. После всех адресных обновлений выполнен итоговый полный прогон, результаты ниже.

## Тестирование

Добавлены 23 метода в `tests/regression/test_layout_corrections.py` с subtests:
- INNER/LEFT/RIGHT/FULL OUTER/CROSS derived JOIN, последовательные и вложенные JOIN, FROM, CTE, INSERT и процедурный DML;
- AS/as/As/aS, обычные/quoted алиасы, несколько FROM-таблиц, column/CAST/CTE AS, непрозрачные alias column lists и function targets;
- комментарии у скобок и алиаса, консервативное сохранение AS при комментарии в промежутке, C001 при неоднозначной привязке;
- SELECT/WITH/INSERT/UPDATE/DELETE, несколько statement, пустые строки, leading block comment, процедурные уровни;
- LF/CRLF/CR/смешанный ввод, BOM, multiline literals/quoted identifiers, оба профиля;
- повторный вызов, независимый строгий validator и exact protected spans;
- конфликт edits, защищённый диапазон, отклонение целой группы, порядок подачи edits, процедурный атомарный отказ;
- отрицательные изменения токенов и сохранение старых границ неподдержанных JOIN-форм.

Четыре публичных regression-метода запущены против замороженного baseline: все четыре воспроизводят дефект (12 неуспешных subcases, 0 ERROR). Это проверка до исправления, а не удалённые/ослабленные тесты.

Baseline: 335 tests → итог 358 tests; добавлены 23 метода, старые тесты не удалены. Исправлены четыре согласованных дефекта, новых FAIL/ERROR нет.

Целевой прогон: **30 tests, 0 FAIL, 0 ERROR**, 81.301 s (последний повтор).

Полный прогон: **358 tests, 0 FAIL, 0 ERROR; 575.074 s**.

Команда:
```sh
PYTHONDONTWRITEBYTECODE=1 /tmp/sql_formatter_b103_venv/bin/python -m unittest discover -s tests -t . -p 'test_*.py' -v
```
Среда: локальная macOS, Python 3.12.8, SQLFluff 4.4.0. Путь к venv — только путь проверочного окружения, не runtime-зависимость проекта.

## Контроль 73 прежних примеров

Все **73/73** примера совпали с baseline побайтно: первый output, повторный output и последовательности диагностических кодов. Каждая пара прошла независимую строгую валидацию и проверку идемпотентности. Список изменившихся идентификаторов пуст; новых различий вне четырёх правил нет. SHA-256 исходников и baseline-output дополнительно сверены с закоммиченным `B103D_OUTPUT_CHECK.json`. Новые результаты сохранены в `B104_OUTPUT_CHECK.json`.

В этот исторический набор не входили четыре минимальных воспроизведения выше; их различия покрыты новыми целевыми тестами, а не скрыты в baseline.

## Ограничения и ручная приёмка

- Не расширены USING, скобочные JOIN-деревья без derived SELECT и иные неоднозначные AST-формы. Полная канонизация произвольных LF-переносов остаётся техническим долгом.
- При комментарии между таблицей, AS и алиасом исходный фрагмент сохраняется; AS не удаляется ценой переноса комментария. Нестандартные target/alias формы не получают разрешения validator на удаление AS.
- Независимые безопасные группы обычного SQL могут применяться при отказе другой группы, как в B2. Процедура сохраняет полный атомарный rollback. Эти гарантии не заменены обещанием глобальной транзакции для всех обычных SQL.
- BOM: сохранена политика B6/B8 — успешный обычный файловый SQL без BOM, процедуры сохраняют BOM; при отказе адаптер возвращает исходные bytes.
- Windows/DBeaver/Tk не запускались. На Windows требуется ручная приёмка derived JOIN/алиасов, обоих профилей, Unicode/окончаний и поведения редактора. Новый GUI/транспорт не добавлен.

## Изменённые файлы

Production: `formatter.py`, `formatter_modules/formatter_clause_gaps.py`.

Тесты: новый `tests/regression/test_layout_corrections.py`; шесть адресных обновлений `test_clause_interactions.py`, `test_commented_lists.py`, `test_cte_layout.py`, `test_join_layout.py`, `test_set_operations.py`, `test_layout_regressions.py` в том же каталоге.

Документация: `docs/FORMATTER_CONTRACT.md`, `docs/ROADMAP.md`, этот отчёт и `docs/archive/B104_OUTPUT_CHECK.json` с проверяемыми результатами сравнения. Предыдущие архивные отчёты не изменены.

`git diff --check`: PASS. Изменения оставлены без коммита для ручной приёмки. B11 не начат.
