# B8 — CP01–CP05 case normalization

Ветка: `feature/b8-case-normalization`. База: B7,
`f287ba4c119eb523b82697f54da78d4ac6dca472`, 282 tests / 0 FAIL / 0 ERROR.
B7, по подтверждению пользователя, работает в DBeaver на корпоративном Windows.
B8 проверялся автоматически на macOS; повторная проверка именно B8 на Windows
остаётся ручной. Merge в master и push не выполнялись.

## Реализация

Новый `formatter_modules/formatter_case.py` загружает проектную .sqlfluff по
абсолютному пути, исключает home/cwd-конфигурации и создаёт rule pack только
CP01, CP02, CP03, CP04, CP05. Проверяется точное множество активных правил.
Используются публичные render/parse/lint_parsed API SQLFluff 4.4.0,
**lint_parsed(fix=False)**. Исправления берутся из violation.fixes (LintFix);
полный fix или SQLFluff-перестройка текста не запускается. Inline sqlfluff/noqa
комментарии не могут включить другие правила или отключить целевой регистр.

CP01: keywords/binary operators/date parts → upper; CP02: unquoted identifiers
→ lower; CP03: functions → upper; CP04: NULL/TRUE/FALSE → upper; CP05: types → upper.
Классификацию выполняют штатные правила Teradata, не regex. CP01/CP03 уже имели
upper в .sqlfluff, добавлены CP02/CP04/CP05. Одних настроек недостаточно:
прежний runtime только парсил, новый case-проход явно получает и применяет fixes.

Проход идёт **после существующей раскладки**. Все изменения переводятся из
нормализованного parser view обратно в оригинал через SourceMap B6 и применяются
одной атомарной группой существующего planner B2. Planner, карта, protected scanner,
legacy guarded_pass и обработчики клауз не менялись.

Каждый fix обязан быть replace одного однозначно сопоставленного leaf-токена,
с тем же AST-типом, исходным raw и точным upper/lower-результатом, без изменения
длины или пробелов. Дублирующиеся диапазоны токенов, конфликтующие предложения,
пересечения с protected spans, parse errors и неподходящие edits отвергаются.
После применения перепроверяются полный путь каждого code-токена в AST
(типы родителей и порядковые позиции), количество и точный разрешённый текст.

## Валидатор

validate_sql_unchanged теперь вычисляет доказанный CP-кандидат исходного SQL.
Для каждой позиции допускается исходный токен либо соответствующий токен
кандидата; сохраняются тип, порядок и AST-область. Все проверки protected sequence,
комментариев и точной допустимости WHERE/HAVING-префиксов оставлены.
Старое отдельное разрешение upper для SELECT/FROM/WHERE удалено: даже оно теперь
требует реального CP-fix. Нет общего casefold или допуска произвольных замен.
Новый отрицательный тест блокирует разрешение регистра при отсутствии CP-предложения.

Публичные сигнатуры formatter.py и адаптера не менялись. При ошибке CP-прохода
format_sql, как и при прежних ошибках проверки, выдаёт исключение; адаптер B7
перехватывает его и возвращает исходные байты (BOM/CRLF/CR включительно), не выдавая
частично форматированный SQL. E004 по-прежнему отказывает до case-прохода.

## Пример

Вход:

```sql
select A.CLIENT_ID, sum(B.AMOUNT)
from DATABASE.CLIENTS A
left join DATABASE.PAYMENTS B on A.CLIENT_ID = B.CLIENT_ID
where A.STATUS = 'ACTIVE' and B.AMOUNT > 100
order by A.CLIENT_ID;
```

Первый и второй проходы:

```sql
SELECT
    a.client_id
    , SUM(b.amount)
FROM database.clients a

LEFT JOIN database.payments b
ON a.client_id = b.client_id

WHERE 1=1
    AND a.status = 'ACTIVE'
    AND b.amount > 100

ORDER BY a.client_id
;
```

Синтетический WHERE 1=1 и раскладка — существующее поведение B7, не изменение B8.
Литерал 'ACTIVE' не меняется. Аналогично `cast(A as varchar(10)), null, true`
становится `CAST(a AS VARCHAR(10)), NULL, TRUE` без изменения пробелов этого
case-прохода; раскладкой занимается прежний форматтер.

## Тесты и сравнение с B7

B7 воспроизведён в отдельном временном git archive, не путём переключения master.
Полный baseline: 282 tests / 0 FAIL / 0 ERROR, 114.156 s. Перехват вызовов
format_sql во время прогона сохранил 643 уникальных успешно обработанных входа.

Для каждого входа сравнивались B8(input), CP-only(B7(input)) и второй проход B8.
E004 должен оставаться исходным без CP. Результат: **643/643 PASS**, 0 расхождений
раскладки/идемпотентности. Из них 46 отличаются от B7 только регистром, 597
полностью совпадают. Отдельная посимвольная проверка подтверждает одинаковую
длину, неизменность каждого whitespace-символа и отсутствие других различий.
Protected spans дополнительно проверяются строгим runtime-валидатором.

Первый прогон со старыми ожиданиями: 282 tests, 31 FAIL, 0 ERROR — устаревшие
регистровые ожидания/отрицательные проверки. Обновления согласованы пользователем.
Golden-файлы не менялись. Изменён только tests/regression/test_formatter.py:
ожидаемый регистр SELECT/DISTINCT/идентификаторов, JOIN, GROUP/ORDER, HAVING,
WITH, set operators, OVER/frames, QUALIFY. Входы, whitespace ожиданий и проверки
идемпотентности/protected spans сохранены. Для HAVING/заголовков разрешённые
преобразования стали положительными проверками; опасные замены сохранились
отрицательными. Для OVER/QUALIFY добавлен отказ от недопустимого смешанного
регистра, а проверка QUALIFY сравнивает точную последовательность токенов после
подтверждённых CP-замен: синтетический 1=1 всё ещё запрещён.

Новый модуль tests/regression/test_formatter_b8.py — 9 методов:
все пять правил, CTE/JOIN/sets/windows, смешанные окончания и protected content,
строгие отрицательные проверки/отсутствие CP-разрешения, адаптер и E004,
отклонение атомарной группы, недействующие inline config/noqa,
неоднозначный Unicode и невалидный AST.

Целевой расширенный прогон: **68 tests / 0 FAIL / 0 ERROR**, 54.235 s.
Финальный отдельный прогон новых тестов: **9/9 PASS**, 4.063 s.
Финальный полный прогон: **291 tests / 0 FAIL / 0 ERROR**, 273.292 s.
Итог относительно B7: +9 тестов; FAIL 0 → 0, ERROR 0 → 0.
Повторное сравнение финального кода: **643/643 PASS**, 0 расхождений.

Команды (PYTHONDONTWRITEBYTECODE=1):

```sh
/tmp/sql_formatter_phase_a/venv/bin/python -m unittest discover -s tests -t . -p 'test_*.py' -v
/tmp/sql_formatter_phase_a/venv/bin/python -m unittest tests.regression.test_formatter.B42JoinTests tests.regression.test_formatter.B53WindowTests tests.regression.test_formatter.B54QualifyTests tests.regression.test_formatter.B33StrictValidatorTests tests.regression.test_formatter.B44HavingValidatorTests tests.regression.test_formatter_b8 -v
```

## Изменённые файлы

- `.sqlfluff`: политики CP02/CP04/CP05.
- `formatter_modules/formatter_case.py`: предложения SQLFluff и безопасное применение.
- `formatter.py`: post-format case-проход и узкая проверка разрешённых замен.
- `tests/regression/test_formatter.py`: согласованные регистровые ожидания.
- `tests/regression/test_formatter_b8.py`: новые проверки.
- `docs/teradata_formatter_contract_v1.1.md`: согласованное дополнение B8.
- `docs/B8_REPORT.md`: этот отчёт.

## Ограничения

Нормализация опирается на классификацию SQLFluff Teradata, не на каталог БД:
существование UDF/объектов и корпоративные особенности имён не проверяются.
В частности, для квалифицированного имени `DB.MyFunc(...)` SQLFluff 4.4.0
не выдаёт CP-правок: имя с квалификатором остаётся неизменным, аргументы
нормализуются только по собственным AST-токенам. Это отдельно проверено тестом.
Колонка `SUM` и функция `sum(...)` различаются: `sum` и `SUM(...)` соответственно.
Composite/non-leaf fixes и Unicode upper/lower с изменением длины отклоняются
консервативно; пример — U+0130 при lower (два code point). Объекты в двойных
кавычках остаются побайтно неизменными. Неподдерживаемые именованные окна
сохраняют E004/fallback. При изменениях AST после регистра весь case-проход
отменяется. Дополнительные lint/parse/validation проходы увеличивают время
обработки; timeout DBeaver нужно перепроверить на больших рабочих запросах.
Прежний LF-технический долг и ограничения транспорта при недоступном файле/
выходном канале не менялись. Новых зависимостей нет.
