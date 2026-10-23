# B10.5a — Performance baseline and profiling

База: B10.4 `c92f310`, замороженный checkout; Python 3.12.8, SQLFluff 4.4.0, macOS. Корпоративные SQL и исходные файлы пользователя не использовались. Зависимости не обновлялись.

## Методика

`tools/benchmark_formatter.py` содержит синтетические нагрузки и измеряет perf_counter: engine, второй проход по уже нормализованному SQL, personal и corporate без GUI. Три повторения каждого режима; медиана, min, max и spread сохранены в [JSON](B105_BENCHMARK_RESULTS.json). Первый вызов каждого сценария записан отдельно, но лишь первый сценарий означает первый вызов движка в процессе. Импорт измерен отдельно.

`tools/compare_performance.py` запускает два изолированных прогретых процесса, baseline → candidate → candidate → baseline, два цикла (четыре наблюдения на версию/сценарий). Каждая выдача и диагностика сравниваются по хешу. Новая request boundary создаётся для каждого измерения. Cold import, CLI и официальный adapter.main (селектор замещён детерминированным personal, GUI не запускается) измерены в новых процессах по три раза; временный cwd другой. SQL идёт через тот же файловый транспорт.

Benchmark не выполнялся одновременно с unittest или другим benchmark. Внешняя нагрузка/частота CPU не контролируются: разброс особенно заметен в больших сценариях. cProfile/trace имеют собственный overhead и не служат latency-замерами; их времена вложены и **не суммируются**.

Воспроизведение (подставить пути отдельных checkout; тот же interpreter):
```sh
python tools/benchmark_formatter.py --root BASELINE --output baseline.json --profile-costs
python tools/benchmark_formatter.py --root CANDIDATE --output candidate.json --profile-costs
python tools/compare_performance.py --baseline BASELINE --candidate CANDIDATE --output alternating.json
python tools/profile_formatter.py --root BASELINE --output phases.json
```

## Baseline: секунды, median [min; max]

| Сценарий | Символов | Engine | Повтор | Personal | Corporate |
|---|---:|---|---|---|---|
| short | 42 | 0.447 [0.383; 0.490] | 0.349 [0.339; 0.357] | 0.408 [0.407; 0.444] | 0.412 [0.411; 0.448] |
| joins | 80 | 0.522 [0.520; 0.525] | 0.636 [0.558; 0.702] | 0.671 [0.665; 0.855] | 0.811 [0.691; 0.842] |
| cte | 95 | 0.526 [0.506; 0.527] | 0.536 [0.527; 0.542] | 0.753 [0.708; 0.855] | 0.677 [0.666; 0.794] |
| in_lists | 65 | 0.487 [0.464; 0.581] | 0.502 [0.502; 0.598] | 0.596 [0.587; 0.672] | 0.782 [0.635; 0.792] |
| clauses | 141 | 1.415 [1.394; 1.602] | 1.289 [1.279; 1.603] | 1.713 [1.622; 1.950] | 1.638 [1.634; 2.098] |
| insert | 227 | 1.200 [1.080; 1.351] | 1.105 [1.075; 1.570] | 2.000 [1.872; 6.309] | 2.022 [1.979; 2.211] |
| statements | 62 | 0.372 [0.314; 0.388] | 0.378 [0.310; 0.819] | 0.776 [0.686; 0.936] | 0.477 [0.445; 0.541] |
| procedure_short | 113 | 0.942 [0.917; 1.101] | 0.887 [0.883; 1.025] | 1.210 [1.132; 1.299] | 1.121 [1.013; 1.231] |
| procedure_large | 1291 | 17.613 [17.457; 18.998] | 18.506 [17.990; 18.849] | 18.288 [17.992; 19.071] | 19.719 [18.265; 20.718] |

Большая процедура содержит пять INSERT SELECT, nested BEGIN и WHILE. В ней есть повторяющиеся DML. Поэтому добавлен независимый `procedure_varied`: пять разных DML с различными литералами. Он участвует в чередующихся замерах, а не маскируется под исходный baseline.

## Схема вызовов и реальные точки измерения

```text
DBeaver -> adapter.main (read bytes, silent descriptors)
  -> select_profile (GUI, исключён из benchmark)
  -> format_bytes -> decode -> format_sql -> adapter_validate -> encode
format_sql обычный SQL
  -> normalize newline / group comment -> SourceLinter parse
  -> AST margin/alias + reparse -> nested boundaries + reparse
  -> planner/apply -> 5 guarded legacy passes (часть снова parse)
  -> validate -> CP01–05 -> validate
format_sql процедура
  -> format_procedure parse/layout
      -> dml -> format_sql(fragment), parse candidate fragment
  -> planner -> CP -> validate
  -> format_procedure(_checking=True): весь layout/validate повторяется
validate
  -> exact protected sequence -> original snapshot
  -> CP(original) -> case-permitted snapshot -> formatted snapshot
  -> narrow token/prefix/table-AS comparison
SourceLinter parse
  -> SourceMap -> config selection -> render -> lexer/parser AST
  -> OriginalSegment только при отличии нормализованного текста
```

SQLFluff строит AST внутри parser.parse; это не независимая непересекающаяся фаза. Primary parse процедуры выделяется trace `parse`; aggregate parse_rendered включает все повторные разборы. SourceMap.build/__post_init__, OriginalSegment, planner/apply, protected_spans, normalize_case и validator измеряются по фактическим функциям. Процедурная проверка второго прохода — trace `repeat`. Подробные phase results приложены после контрольного прогона; отсутствующая функция означает 0 вызовов в этой нагрузке, а не пропущенную работу.

## Подтверждённые затраты baseline

Один instrumented run: format_sql 46.057 s; parse_rendered 177 вызовов / 39.447 s inclusive; SourceLinter.parse_string 143 / 32.050 s; validate_sql_unchanged 22 / 22.821 s; _validation_snapshot 66 / 17.020 s; normalize_case 34 / 10.244 s. FluffConfig.from_path 172 / 3.118 s. Времена перекрываются: validator включает parse/CP, процедура — DML и повтор.

Вывод: повторный parse/доказательство одинакового текста является измеренным bottleneck. Чтение/создание конфигураций менее значимо; оно не оправдывает сейчас cache mutable FluffConfig или изменение конфигурационной архитектуры. Layout-правила не переписываются, внутренний второй проход процедуры не отключается.

## Выбранная оптимизация и риски

Сохраняются только value-results: доказанный CP-текст и снимок tokens/comments/predicate scopes/optional-AS permissions. Cache ограничен одним синхронным публичным вызовом, вложенные DML используют его; на выходе или исключении очищается. Никаких AST/Linter/config/edit/full-format-result в cache. Ключ включает точный исходник, абсолютный идентификатор config и точные bytes файла. После edits другой текст не попадает в старые координаты. Снимки защищены defensive copy; исключения не кэшируются. Между вызовами/профилями/потоками нет переноса состояния. Ограничения: 32 результата, 200000 символов исходных ключей, 64000 на запись; большие значения вычисляются обычным путём.

Риски: ошибочный ключ, mutable result leak, незавершённый lifecycle, смешение профилей. Закрыты отдельными unit-тестами. Если в будущем появляется resolver, его effective fingerprint должен заменить ключ file-bytes до включения разных policies. Нельзя использовать текущий механизм как долгоживущий cache. Adapter с redirect_stdout/stderr остаётся синхронным API; этот этап не объявляет весь GUI/adapter потокобезопасным.

## Чередующееся сравнение

| Нагрузка | Baseline median [min; max] | Candidate median [min; max] | Отношение медиан B/O |
|---|---|---|---:|
| short | 0.300 [0.294; 0.374] | 0.231 [0.230; 0.243] | 1.30× |
| insert | 1.038 [1.009; 1.359] | 0.870 [0.796; 1.015] | 1.19× |
| procedure_large | 12.930 [10.259; 16.978] | 6.755 [5.148; 8.732] | 1.91× |
| procedure_varied | 10.444 [10.369; 16.120] | 9.183 [6.992; 14.725] | 1.14× |

Процедура с одинаковыми DML выигрывает заметно. Для разных DML наблюдения перекрываются и имеют большой разброс; стабильный процент ускорения для такого класса не доказан. Это ограничение результата, не повод отключать проверки или принимать предполагаемое универсальное ускорение. На VDI нужны дополнительные парные замеры. Короткий SQL и INSERT по медианам не ухудшились. Цель 5–8 секунд не обещается для произвольных процедур.

## Cold process, секунды

| Режим | Baseline | Candidate |
|---|---|---|
| import | 0.393 [0.378; 0.487] | 0.354 [0.311; 0.438] |
| cli | 0.990 [0.976; 1.099] | 0.949 [0.888; 1.081] |
| adapter | 1.022 [1.018; 1.317] | 0.986 [0.946; 1.041] |

Cold samples включают запуск процесса; импорт отдельно не вычитается из CLI, потому что это разные наблюдения с шумом. Для короткого SQL реальная задержка DBeaver близка к полной cold adapter задержке плюс пользовательский диалог, а не только warm engine. Personal/Corporate совпадают по SQL; различия времени между ними в последовательном benchmark не означают разной логики.

## Полный unittest

Свежий baseline: **358 tests, 0 FAIL/ERROR, 651.148 s**. Candidate: **369 tests, 0 FAIL/ERROR, 357.474 s** (добавлены 11 unit-тестов). Отношение длительностей 1.82×; уменьшение около 45%. Предыдущий candidate прогон: 368 tests / 427.306 s; разброс общего времени показывает, почему это не статистический SLA. Дополнительный targeted прогон — 42 tests PASS плюс отдельный budget test PASS.

Это отдельная интеграционная нагрузка, не замена измерению одного SQL. Baseline и candidate прогоны последовательные, не ABBA; единичное сравнение общей длительности описательное, не статистический performance SLA.

## Подробные фазовые замеры

[Полный cProfile и trace](B105_PHASE_RESULTS.json). Отдельный instrumented запуск каждой версии, не latency benchmark. Times inclusive, вложенные фазы не складывать. Trace включает файловую запись, а cProfile меняет время; counts надёжнее сравнивать, чем абсолютные секунды между разными инструментированными запусками.

| Фактическая функция | Baseline calls / seconds | Candidate calls / seconds |
|---|---:|---:|
| SourceMap.build | 189 / 0.135369 | 100 / 0.070519 |
| OriginalSegment.__init__ | 0 / 0.000000 | 0 / 0.000000 |
| FluffConfig.from_path | 172 / 1.966512 | 83 / 0.931100 |
| Linter.__init__ | 177 / 0.001249 | 88 / 0.000563 |
| Linter.parse_rendered | 178 / 23.880900 | 89 / 11.812685 |
| plan_edits | 78 / 0.007775 | 49 / 0.007745 |
| apply_edits | 73 / 0.000367 | 44 / 0.000318 |
| normalize_case | 34 / 6.554185 | 5 / 1.784819 |
| protected_spans | 229 / 0.062515 | 200 / 0.052549 |
| validate_sql_unchanged.<locals>.protected_values | 44 / 0.013989 | 44 / 0.013628 |
| validate_sql_unchanged | 22 / 14.940763 | 22 / 2.992803 |

OriginalSegment не вызывается в этой LF-нагрузке; это не утверждение нулевой стоимости CRLF-map. CRLF/CR correctness покрыта полным unittest и B10.4 matrix. SourceMap и round-trip проверки не отключены.

| Процедурная trace-стадия | Baseline seconds | Candidate seconds |
|---|---:|---:|
| parse | 0.5811, 0.6160 | 0.5843, 0.6114 |
| layout | 10.4748, 10.4018 | 5.9717, 4.7654 |
| planner | 0.0063, 0.0003 | 0.0065, 0.0002 |
| case | 0.6696, 0.6615 | 0.6500, 0.0003 |
| validate | 2.3416, 2.6393 | 1.8214, 0.0762 |
| repeat | 14.3418 | 5.4754 |

Парные записи соответствуют первому и внутреннему повторному проходам процедуры. Repeat по-прежнему выполняется полностью. Planner, protected checks и strict comparisons остаются вызванными, сокращены повторные вычисления proof values.

### Последняя проверка error-path

При недоступном служебном fingerprint-файле memoization обходится, исходный loader и все проверки работают как прежде. Эта ветка не меняет обычный путь и не создаёт нового config fallback. После правки выполнены 11 unit-тестов request cache, полный набор 369 tests и повторный performance smoke на short/procedure_large (по два измерения каждого режима). Все SQL-хеши прежние. Samples находятся в `final_error_path_smoke` benchmark JSON; это отдельный нечерёдующийся запуск, поэтому его времена не используются для вывода о сравнительном ускорении.

### Официальный adapter.main без GUI: trace стадий

Отдельный cold subprocess с временным UTF-8 файлом и детерминированным селектором personal. stdout совпадает по SHA-256, stderr пуст. Это instrumented stage sample, не статистический latency benchmark и не Windows-приёмка.

| Стадия | Baseline ms | Candidate ms |
|---|---:|---:|
| read | 0.81 | 0.495 |
| profile | 0.1 | 0.097 |
| decode | 0.225 | 0.24 |
| adapter_format | 441.065 | 365.889 |
| adapter_validate | 58.224 | 63.549 |

Воспроизведение: `python tools/profile_formatter.py --root CHECKOUT --output adapter-phases.json --adapter-only`. Время profile здесь — только вызов mock-selector, не человеческий диалог.
