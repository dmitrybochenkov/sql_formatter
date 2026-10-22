# B10.1 — изолированный прототип процедур Teradata

База: B9 `fc7b7ec0cceb854df4fe89b0517019ff52983cd0`, 304 tests / 0 FAIL / 0 ERROR.
Ветка: `feature/b10-stored-procedures`. Среда: macOS, Python 3.12.8, SQLFluff 4.4.0.

## Результат и границы

Синтетическая процедура полностью разобрана без lexical violations и `unparsable`.
У каждого BEGIN/WHILE есть собственный закрывающий END/END WHILE в том же AST-узле.
DECLARE разрешён только в начале своего BEGIN-блока. Каждый исполняемый оператор
обёрнут в `procedure_executable` со своим обязательным `;`.

Это parser-прототип, **не реализация форматирования процедур**. Он не импортируется
production-кодом, не меняет глобальный реестр диалектов и установленную библиотеку.
Форматтер, CP01–CP05, DBeaver, golden и правила B8/B9 не изменены. Production по-прежнему
отклоняет процедуру; оба профиля возвращают исходные байты, включая BOM и CRLF.

## Реализация

- `prototypes/__init__.py`: явное пространство изолированных экспериментов.
- `prototypes/teradata_procedures.py`: приватная копия Teradata и 9 типов процедурных
  AST-сегментов плюс корень файла; только прямой вызов `parse_procedure()` включает её.
- `tests/unit/test_procedure_prototype.py`: 15 parser/isolation-тестов и 2 отдельные
  проверки существующих дефектов DML. Старые тесты не менялись.
- `docs/B101_SYNTHETIC_AST.txt`: полный фактический AST синтетической процедуры.
- Этот отчёт: матрица, воспроизведение, ограничения и план следующего решения.

Использованы штатные SQLFluff Sequence/OneOf/Bracketed/Delimited/Ref. Новая грамматика
не содержит Anything, raw-блоков или regex-разбиения. DELETE и INSERT SELECT используют
существующие сегменты Teradata, с явным ограничением по `SemicolonSegment` внутри
процедурного оператора. Без этой границы вложенный SELECT пытался продолжить разбор
за концом INSERT. Строки и комментарии разбирает штатный lexer: `;` внутри них не
становится разделителем оператора.

В SQLFluff 4.4.0 нет публичного параметра для передачи пользовательского Dialect
непосредственно Parser/Lexer. Прототип задаёт `config._configs['core']['dialect_obj']`
на **своём экземпляре** FluffConfig. Этот единственный частный hook изолирован,
ограничен проверкой точной версии 4.4.0 и не меняет установленную библиотеку.
Перед B10.2 нужно принять и протестировать этот механизм для всех потребителей AST;
сейчас ни runtime, ни case-проход его не используют.

## Матрица поддержки

| Конструкция | Результат | AST / проверка |
|---|---|---|
| CREATE / REPLACE PROCEDURE, qualified name | PASS | procedure_definition |
| Параметры IN / OUT / INOUT / без явного режима | PASS | procedure_parameter, data_type |
| DATE, INTEGER, DECIMAL(p,s), VARCHAR(n), quoted parameter | PASS | существующая DatatypeSegment |
| SQL SECURITY INVOKER / отсутствие security-клаузы | PASS | procedure_security |
| BEGIN/END, вложенный BEGIN | PASS | рекурсивный procedure_block |
| DECLARE, несколько переменных, DEFAULT literal | PASS | procedure_declaration; только до executable |
| Последовательные SET, арифметика, CAST | PASS | procedure_assignment, expression |
| WHILE/DO/END WHILE, вложенные и последовательные циклы | PASS | рекурсивный procedure_while |
| CALL, 0/несколько аргументов, функции в аргументах | PASS | procedure_call, bracketed/expression |
| DELETE внутри цикла | PASS | delete_statement внутри procedure_executable |
| INSERT SELECT, INNER/LEFT JOIN, CASE, вложенный SELECT | PASS | insert_statement → select_statement |
| IN / NOT IN, скобки, TIMESTAMP / INTERVAL, конкатенация | PASS | существующая грамматика выражений |
| Line/block comments между операторами и ключевыми словами | PASS | точные исходные листья и slices |
| Unicode, quoted identifiers, многострочный литерал/comment | PASS | точное сохранение каждого символа |
| `; -- DO END` внутри строк | PASS | нет ложных блоков или terminator |
| Однострочный SQL; повторный parse | PASS | одинаковые raw и AST-дампы |
| Пропущенные/неверные END, DO, `;`, скобки, аргументы | отказ | complete=False / unparsable / lexer violation |
| Склеенный DOCALL, malformed DELETE/INSERT, поздний DECLARE | отказ | нет непрозрачного fallback |
| IF/FOR, labels, cursors, UPDATE, standalone SELECT внутри body | отказ | вне согласованного минимального подмножества |
| Несколько процедур/произвольный SQL-script | вне области | корень принимает ровно одну процедуру |
| CRLF/CR | явный отказ прототипа | SourceMap ещё не интегрирован; production B6 неизменён |

Положительные проверки не объявляют полную поддержку Teradata SQL/PSM. Parser не
проверяет существование таблиц/переменных, типы выражений или права исполнения.
Пустой BEGIN принимается; тело WHILE должно иметь хотя бы один оператор.
DEFAULT ограничен LiteralGrammar. Метки, handlers, cursors, IF/FOR/REPEAT/LOOP,
SQL SECURITY DEFINER/OWNER, дополнительные атрибуты процедуры не реализованы.
Отсутствие unparsable — необходимое, но не достаточное основание будущего форматирования.

## Синтетическая процедура и дерево исполнения

Точный SQL находится в константе SYNTHETIC тестового модуля; содержит 3 DECLARE,
4 SET, 1 WHILE, 1 CALL, 1 DELETE, 1 INSERT с двумя JOIN и вложенным SELECT.
Ни корпоративных имён, ни пользовательского SQL в тестах нет.

Сокращённое дерево, проверяемое независимо от строкового представления:

```text
file
  procedure_definition [REPLACE PROCEDURE example_proc]
    procedure_parameter [IN p_start_date DATE]
    procedure_parameter [OUT p_count INTEGER]
    procedure_security [SQL SECURITY INVOKER]
    procedure_block [BEGIN … END]
      procedure_declaration [v_cur_date DATE] ;
      procedure_declaration [v_end_date DATE] ;
      procedure_declaration [v_count INTEGER DEFAULT 0] ;
      procedure_executable → procedure_assignment [v_cur_date = p_start_date] ;
      procedure_executable → procedure_assignment [v_end_date = p_start_date + 2] ;
      procedure_executable
        procedure_while [WHILE v_cur_date <= v_end_date DO … END WHILE]
          procedure_executable → procedure_call ;
          inline_comment
          procedure_executable → delete_statement → where_clause ;
          block_comment
          procedure_executable
            insert_statement → select_statement
              select_clause [a.id, b.name, CASE … END]
              from_clause [example_source, INNER JOIN, LEFT JOIN]
              where_clause [IN, NOT IN (select_statement)]
            ;
          procedure_executable → procedure_assignment [v_cur_date + 1] ;
        ;
      procedure_executable → procedure_assignment [p_count = v_count] ;
  ;
```

Фактическое дерево: [B101_SYNTHETIC_AST.txt](B101_SYNTHETIC_AST.txt).
Тест проверяет 12 структурных terminator, порядок операторов блока и цикла,
принадлежность DELETE/INSERT циклу, точность source_slice каждого листа и сборку
оригинала из листьев без потери/удвоения символов. Повторный parse проверяет
стабильность AST, а не идемпотентность ещё не реализованного форматирования.

## Сохранённые дефекты DML — без исправлений

1. `INSERT INTO example_target SELECT a.id, b.name FROM example_source a INNER JOIN example_other b ON a.id = b.id WHERE a.id IN (1, 2);`
   Первый проход вставляет один LF перед INNER JOIN, второй добавляет ещё один.
   Обе диагностики пусты. Тест явно фиксирует `second != first` и точное отличие.
2. `DELETE FROM example_target WHERE id IN (1, 2) AND status = 'OK';`
   Actual: тот же SQL с `;` на отдельной строке. Широкая WHERE-правка отклонена с
   SQLFMT-E002; повторный результат стабилен, литерал сохранён.

Это воспроизводящие тесты известных ограничений, не новое golden-ожидание и не
доказательство исправления. При согласованном исправлении в будущем их assertions
нужно заменить проверками корректного результата и идемпотентности.

## Оценка B10.2

Сложность **средняя–высокая**: синтаксическое вложение подтверждено, но подключение
не сводится к одной замене Linter. Предлагается согласовать отдельные шаги:

1. Единый ограниченный выбор грамматики для runtime, case-нормализации и validator;
   SourceMap и protected spans для CRLF/CR/BOM. Сохранить обычный Teradata путь B8/B9.
2. Проверка процедурного дерева: типы, порядок и родители операторов, пары блоков,
   terminator, параметры; whitelist case-fixes без ослабления прежних гарантий.
3. Только затем layout по AST-глубине, процедура как единая атомарная транзакция edits;
   неоднозначные комментарии или отказ любой стадии возвращают весь оригинал.
4. Отдельное ограниченное исправление INSERT SELECT/DELETE, доказанное тестами выше;
   исключить процедурные terminator из общего правила переноса всех `;`.
5. Полная матрица двух проходов, CP01–CP05, protected spans, оба профиля, обычный SQL.

Никакой из этих шагов в B10.1 не выполнен. Реальный исходный .sql пока не предоставлен;
синтетический успех не означает покрытие корпоративной процедуры. Windows/DBeaver
остаются отдельной ручной проверкой. B10.2 требует согласования.

## Результаты проверок

Целевые: `python -m unittest tests.unit.test_procedure_prototype -v` — **17 / 0 / 0**.
Полные: `python -m unittest discover -s tests -t . -p 'test_*.py' -v` — **321 / 0 / 0**.
Все 304 прежних теста и 17 новых прошли. Никаких новых FAIL/ERROR; два известных
дефекта DML не исправлены и явно воспроизводятся своими тестами.
Использован `/tmp/sql_formatter_phase_a/venv/bin/python` с
`PYTHONDONTWRITEBYTECODE=1`. Итог полного прогона:

```text

----------------------------------------------------------------------
Ran 321 tests in 229.823s

OK
```

`git diff --cached --check` — без ошибок. В коммите только 5 новых файлов прототипа,
тестов и документации. Установленная библиотека и существующие файлы не редактировались.
Merge в master и push не выполняются на этом parser-подэтапе.
