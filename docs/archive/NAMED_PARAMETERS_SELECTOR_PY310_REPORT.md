# Named parameters, Personal selector and Python 3.10

Дата: 09.11.2026. Ветка `feature/b10-5f-user-profiles`, база `0d8ad3e` (clean перед работой). Commit/push/merge не выполняются. Реальные корпоративные SQL, имена объектов и пути не включались; SQL ниже и в тестах синтетический.

## Причина и решение для Teradata parameters

Чистый `Linter(dialect='teradata')` SQLFluff 4.4.0 возвращает `unparsable` для `SELECT id FROM events WHERE report_date=:Calc_Date;`. В ANSI/унаследованной Teradata lexer есть `colon`, но в выражениях нет грамматики `:name`. Это отказ parse, а не GUI, CP, protected spans или чтения DBeaver.

`formatter_modules/teradata_parameters.py` расширяет **приватную копию** диалекта. Lexer распознаёт `:[A-Za-z_][A-Za-z0-9_]*` после лексеров строк/комментариев/`::`, до одиночного colon. AST-leaf `named_parameter` имеет точный source range и исходные байты. Штатный parser обрабатывает его как значение выражения. Ни замены на литералы, ни маскирования, ни templater-подстановок нет. Установленная SQLFluff и глобальный registry не меняются.

Расширение включено через существующий `select_config()` в обычном runtime, CP01–CP05 и процедурной грамматике. Код без двоеточий сохраняет прежнюю обычную конфигурацию. В процедурах применяется та же grammar-функция. Имена параметров не являются naked identifiers/keywords, поэтому CP не меняет их. Строгий validator сохраняет количество, тип, порядок, ownership и написание параметров; проверки protected spans, source map, planner и атомарного rollback не ослаблены.

Выявленная при реализации тонкость: добавление bind в LiteralGrammar само по себе позволяло ANSI SELECT-element ветке `DatatypeSegment + LiteralGrammar` принять `id:Other`. Для этой ветки сохранена исходная грамматика литералов `UnboundLiteralGrammar`. `id:Other` отклоняется; поддерживаемые типизированные литералы и касты сохраняются. Этот случай закреплён отрицательным тестом.

### Минимальный пример

Вход:

```sql
select t.report_date,t.id from events t where t.report_date=:Calc_Date and t.id is not null;
```

Actual = expected:

```sql
SELECT
    t.report_date
    , t.id
FROM events t

WHERE 1=1
    AND t.report_date = :Calc_Date
    AND t.id IS NOT NULL
;
```

Поддержаны SELECT, WHERE, JOIN ON, HAVING, CASE, вызовы функций, IN/BETWEEN, повторные/разные параметры, CTE, UNION ALL, вложенный SELECT и процедурный DML. Сложный `tests/manual/input.sql` сочетает эти области с OVER, positional GROUP BY, комментариями и смешанным регистром. Он проходит parse/layout/CP/validation/repeat без отказов. Строки и quoted identifiers с двоеточием, комментарии, CR/LF/CRLF внутри protected spans и `::` проверены отдельно.

Не обещается поддержка произвольного синтаксиса параметров: числовое начало, пробел после colon, quoted/Unicode bind names, подстановка имён таблиц и неизвестные конструкции не добавлены. Настоящий parse error сохраняет исходные байты адаптера, включая BOM/CRLF.

## Personal и таймер

Пять SQL-групп и Corporate values не изменены. Новая UI-секция `profile_selector.timeout_seconds`: int 1–60, bool/float/string/0 отклоняются, default 3 для старых файлов. Секция валидируется, но не входит в сравнение SQL-стиля и fingerprint SQL-политики; изменение только таймера не включает селектор.

| Состояние | Действие |
|---|---|
| Personal отсутствует/удалён | Corporate немедленно, без GUI/таймера |
| Валидный Personal совпадает по SQL-стилю | Corporate немедленно |
| Валидные отличия | Единственное окно на каждый вызов, компактное число отличий |
| `1` / кнопка Personal | Personal немедленно |
| `2` / кнопка Corporate | Corporate немедленно |
| Истёк timeout | **Personal** |
| Esc / крестик | Отмена, исходные байты |
| Ошибка GUI | Исходные байты |
| Невалидный Personal | Corporate + прежнее однократное предупреждение об ошибке |

Отдельное OK-уведомление о валидных изменениях/отличиях/исправлении удалено. `profile_state.json`, lock и atomic replace остаются только для дедупликации **ошибок конфигурации**; при исправлении/удалении запись молча очищается, для валидного Personal state не создаётся. Полезная безопасная диагностика ошибок сохранена.

Таймер: monotonic deadline, Tk `after`, обновление countdown, без потоков/глобального перехвата. Общий `finish()` с флагом finished принимает только первое решение и отменяет callback таймера. Тесты проверяют обе очередности совпадения клавиши и timeout; позднее событие не запускает второй профиль. Snapshot Personal перед окном неизменен до конца вызова. stdout/stderr остаются только транспортом SQL адаптера; справка доступна лишь в CLI `formatter.py -h/--help`.

## Python и диагностика

`tomllib` используется на 3.11+; на 3.10 импортируется `tomli==2.2.1` с marker `python_version < "3.11"` в requirements. SQLFluff 4.4.0 объявляет Requires-Python >=3.10. Реальные отдельные окружения: CPython 3.10.21 и 3.12.8, SQLFluff 4.4.0, pytest 9.2.0 на macOS. `uv pip check` прошёл в обоих. На Python 3.10 фактически импортированы tomli 2.2.1 и tkinter (Tk 9.0), но графическое окно не открывалось. Транзитивные зависимости могут различаться по Python; полный lock/wheelhouse не создавался.

CLI корректно обрабатывает одиночные `-h`/`--help` до чтения файла; файловый режим, default input.sql и интерфейс адаптера не меняются. Subprocess-тесты запускают CLI/адаптер на обоих интерпретаторах.

SourceLinter пишет opt-in метаданные отказа через существующий trace: stage=parse, UNPARSABLE/LEXICAL_ERROR, тип сегмента, offset, line/column при наличии AST marker, allowlisted error_type. Столбец — начало проблемного AST-сегмента, а не обязательно конкретный неверный символ. SourceMap сохраняет координаты для CRLF/CR. Для `where id = :;` начало нераспознанного сегмента — колонка 10 (оператор `=`). SQL, literals, имена, пути и исключения с payload не логируются. Инструмент `tools/diagnose_formatter.py` и переменные opt-in не изменены.

## DBeaver: причина задержки и ручные действия

В [исследованном официальном SQLFormatterExternal.java](https://github.com/dbeaver/dbeaver/blob/devel/plugins/org.jkiss.dbeaver.model.sql/src/org/jkiss/dbeaver/model/sql/format/external/SQLFormatterExternal.java) завершение проверяется после сна `timeout / 10` (строки 56–60 на дату исследования). Поэтому 120000 ms может дать минимум 12 секунд ожидания UI даже при быстром процессе; 3000 ms даёт более частые проверки, но не вмещает таймер 3 с и обработку. Это объяснение из исходного кода, а не результат запуска установленной версии на VDI.

Минимальное решение — одно окно и подбор штатного Exec timeout. Начальная рекомендация для коротких запросов: **10000 ms**, с проверкой бюджета startup + selector + format/validation + запас. Для длинных процедур увеличить по измерениям, например до 30000–60000 ms или более. Слишком большой timeout может увеличить задержку опроса; универсальная гарантия длительности не даётся. Ни скрытого чтения настроек, ни автоматического изменения DBeaver, daemon/EXE или обходных механизмов нет.

Полные команды и шаги: [tests/manual/README.md](../../tests/manual/README.md). Реальная Windows, UNC-запуск, фокус, human countdown, msvcrt-lock и конкретная версия DBeaver **не проверены**. В репозитории подготовлен только synthetic `tests/manual/input.sql`.

## Проверки

Оба полных прогона завершились exit 0:

| Среда | Команда | Результат |
|---|---|---|
| CPython 3.10.21 / tomli 2.2.1 | `python -m pytest tests -q` | **430 passed, 778 subtests passed**, 353.29 s |
| CPython 3.12.8 / tomllib | `python -m pytest tests -q` | **430 passed, 778 subtests passed**, 360.12 s |

Относительно принятой базы 413/743: +17 тестов, +35 subtests, 0 FAIL / 0 ERROR. Время full suite не является performance benchmark: прогоны и сравнение выполнялись параллельно. Целевые проверки после исправления грамматики: 12 tests / 24 subtests PASS; UI/config contracts: 37 tests / 106 subtests PASS.

[Corporate equivalence](NAMED_PARAMETERS_EQUIVALENCE.json): отдельные запуски `tools/check_equivalence.py` по frozen `git archive HEAD` базы и рабочему дереву дали побайтно идентичные JSON-результаты. Сравнены 73 historical ID, 43 уникальных B10.4 input, 4 отказа; output, повтор, оба профиля, diagnostics и strict validation совпали. Оба запуска дополнительных 23 B10.4 tests — PASS. `git diff --check` — PASS.

Headless subprocess-запуски CLI/адаптера выполнены обоими реальными интерпретаторами; fake-Tk проверяет countdown, ручные клавиши/мышь, остановку таймера, обе очередности race, Esc/крестик, отсутствие лишнего алерта и однократную отправку в движок. Дополнительно: snapshot при изменении файла, ошибочная конфигурация, конфиденциальность parse trace и комментарии Corporate в шаблоне. Старые SQL golden не изменялись. Прежние тесты уведомлений адресно обновлены под удаление только валидных алертов; error-deduplication, fail-safe, stdout, snapshot и конкурентная запись сохранены и продолжают проверяться. Fake-Tk scheduler использует управляемые часы, реального ожидания 3 с в suite нет.


## Локальные замеры запуска

После завершения полных тестов: три свежих subprocess адаптера на сценарий, без GUI, Corporate при отсутствующем Personal (путь подменён только в измерительном test seam). SQL короткий и сложный synthetic; stderr пуст, exit 0, результат стабилен и одинаков между Python. [Samples и SHA-256](NAMED_PARAMETERS_TRANSPORT_TIMINGS.json).

| Среда | Короткий SQL, median s | Сложный synthetic SQL, median s |
|---|---:|---:|
| Python 3.10.21 | 0.580 | 1.667 |
| Python 3.12.8 | 0.965 | 2.017 |

Эти серии не доказывают преимущество версии Python и не измеряют UNC/VDI/DBeaver или человеческий выбор. Реальный таймер добавляет до заданного числа секунд к процессу; сетевой startup и длительная процедура требуют отдельного запаса timeout. Механизм повторной проверки/CP/SQLFluff runtime не оптимизировался и не отключался.

## Изменённые файлы

- `README.md`
- `config_templates/personal.example.toml`
- `dbeaver_adapter.py`
- `docs/DBEAVER_WINDOWS_SETUP.md`
- `docs/FORMATTER_CONTRACT.md`
- `docs/ROADMAP.md`
- `docs/USER_CONFIGURATION.md`
- `docs/archive/NAMED_PARAMETERS_EQUIVALENCE.json`
- `docs/archive/NAMED_PARAMETERS_SELECTOR_PY310_REPORT.md`
- `docs/archive/NAMED_PARAMETERS_TRANSPORT_TIMINGS.json`
- `formatter.py`
- `formatter_modules/formatter_config.py`
- `formatter_modules/formatter_dialect.py`
- `formatter_modules/formatter_runtime.py`
- `formatter_modules/formatter_trace.py`
- `formatter_modules/profile_notifications.py`
- `formatter_modules/profile_selector.py`
- `formatter_modules/teradata_parameters.py`
- `formatter_modules/teradata_procedure_grammar.py`
- `requirements.txt`
- `tests/contract/test_adapter.py`
- `tests/contract/test_adapter_profiles.py`
- `tests/contract/test_diagnostics.py`
- `tests/contract/test_optional_personal.py`
- `tests/contract/test_python310_and_parse_diagnostics.py`
- `tests/contract/test_user_profiles.py`
- `tests/helpers/runners.py`
- `tests/manual/README.md`
- `tests/manual/input.sql`
- `tests/regression/test_named_parameters.py`
- `tests/unit/test_profile_selector.py`
- `tools/benchmark_profile_selection.py`
- `tools/compare_performance.py`
- `tools/profile_formatter.py`


Итог: изменения готовы для ревью в текущей ветке. Commit, push, merge, deployment и настройка DBeaver не выполнялись. Ручная Windows-приёмка остаётся открытой; дальнейшие этапы не начаты.


## Финальная проверка перед публикацией

После отдельного разрешения владельца выполнена проверка всех 34 изменённых/новых файлов: scope соответствует задаче, golden/защитный planner не изменены, diff-check чистый. Подтверждены полные прогоны 430 tests / 778 subtests на Python 3.10 и 3.12 и точная Corporate equivalence 73 + 43 + 4. После этих прогонов менялась только документация. Приватный образец, корпоративные имена, реальные пользовательские пути и секреты в наборе изменений не обнаружены; SQL и Windows-пути тестов синтетические. Разрешены один commit и push в текущую feature-ветку; merge/rebase/main исключены. SHA и подтверждение удалённой ветки сообщаются после выполнения Git-операций.
