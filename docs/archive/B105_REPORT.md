# B10.5 — Performance & Configuration Architecture

## Состояние и границы

База: B10.4 `c92f310` (`feat: correct SQL layout and normalize table aliases`), проверенное чистое рабочее дерево. Работа в `feature/b10-5-performance-config`. Baseline заморожен в отдельном checkout из git archive; сравнение не использует незакоммиченный B10.4. Python 3.12.8 / SQLFluff 4.4.0, macOS; существующее окружение, без установки/обновления зависимостей.

Корпоративный SQL, пользовательские файлы и приватные логи не использовались. В репозиторий не добавлены личные пути. Commit/merge/push/deployment не выполнялись.

## Измерение и изменение runtime

[Baseline и методика](B105A_PERFORMANCE_BASELINE.md), [машиночитаемые замеры](B105_BENCHMARK_RESULTS.json).

Подтверждённый bottleneck — повторный parse/построение доказательств одного и того же SQL. Для большой синтетической процедуры baseline выполняет 177 SQLFluff parse_rendered и 66 validation snapshots. Это измерено, а не предположение по чтению кода.

Реализована одна ограниченная оптимизация с двумя consumers:

- request-local повторное использование точного CP01–CP05 результата;
- request-local повторное использование value snapshot строгого валидатора.

Кэшируются не решения «SQL безопасен» и не итог форматирования: каждый validate вызов снова сравнивает текущие tokens, narrow exceptions и protected spans, а процедура снова выполняет layout/внутренний repeat. SQLFluff AST, Linter, конфигурация и edits не кэшируются. Старые координаты не переиспользуются: ключ — точный текст и точные bytes действующей конфигурации. Данные снимков копируются; исключения не сохраняются. Если служебное чтение fingerprint недоступно (OSError), выполняется исходная функция без memoization: это не подстановка настроек, а сохранение прежней семантики loader/ошибок. Отдельный тест подтверждает отсутствие нового отказа из-за оптимизации.

Жизненный цикл ограничен синхронным format_sql/validate_sql_unchanged вызовом. Nested DML разделяет только этот request. `finally` очищает память и сбрасывает ContextVar; thread owner и active guard изолируют унаследованные/истёкшие контексты. Внешние вызовы, профили и предыдущие SQL не наследуют proofs. Лимиты записей/символов приводят к обычному вычислению, не к отказу или изменению SQL.

Другие гипотезы сознательно не реализованы: mutable AST/Linter cache, глобальная конфигурация, переписывание legacy-проходов, исключение второго прохода, ускорение путём пропуска strict validation. Конфигурационный resolver отложен до согласования.

## Производительность

| Сценарий | Baseline median, s | Candidate median, s |
|---|---:|---:|
| short | 0.300 | 0.231 |
| insert | 1.038 | 0.870 |
| procedure_large | 12.930 | 6.755 |
| procedure_varied | 10.444 | 9.183 |

Cold adapter median: 1.022 → 0.986 s. Все min/max/spread и исходные samples доступны в benchmark JSON.

Разброс large/varied заметный. Для varied отдельные candidate samples медленнее некоторых baseline samples; устойчивый проигрыш или универсальный процент выигрыша не установлен. Не принимаем эти наблюдения за гарантию для произвольной процедуры. Оптимизация оставлена для ревью вместе с исходными samples; на VDI нужны повторные парные измерения. Cold latency короткого SQL в основном включает startup и проверяется отдельно; время GUI не измерялось.

## Функциональная проверка

Целевые проверки: 42 tests, 0 FAIL/ERROR, 53.047 s; дополнительно тест суммарного бюджета ключей — PASS. Финальный набор request-local тестов — **11/11 PASS, 4.514 s**, включая недоступный fingerprint. Новые тесты проверяют defensive copies, точные CR/LF и config bytes в ключе, exceptions, cleanup, copied contexts/threads, entry/total budgets, negative validator, последовательные профили и обязательный procedural repeat.

Полные наборы: baseline **358/358 PASS (651.148 s)**, candidate **369/369 PASS (357.474 s)**. Нет FAIL/ERROR; добавлены 11 unit-тестов, существующие тесты/ожидания не изменены.

**Эквивалентность PASS:** 73 исторических ID, 43 уникальных входа, захваченных check helper B10.4, и 4 дополнительных сценария отказа совпали побайтно/по кодам с baseline. Оба профиля и повторный проход проверены. B10.4 suite выполнен отдельно на обеих версиях: 23/23 PASS; последняя сверка после error-path исправления также 23/23 PASS. [Хеши и коды](B105_EQUIVALENCE.json), [подробные фазовые измерения](B105_PHASE_RESULTS.json).

73 исторических ID проверяются по исходным SHA-256 B10.4. Они содержат исторические повторы; инструмент выполняет одинаковый уникальный вход один раз, но сохраняет каждый ID и его результат. Сравниваются первый/второй output, диагностика, оба профиля и strict validation. Отдельно выполняется вся B10.4 regression matrix и записываются результаты её публичного check helper; отрицательные/transport тесты также выполняются целиком. Добавлены отдельные invalid/E004/C001 входы. Никакие golden или прежние ожидания не менялись.

## Конфигурационный аудит и предложение

[Полный каталог](B105E_CONFIGURATION_INVENTORY.md) и [520 записей с требуемыми полями](B105_CONFIGURATION_INVENTORY.json). Включены effective parser/CP defaults SQLFluff, внутренние Python arguments, layout, profiles, transport, environment, diagnostics, safety и новые непубличные лимиты request cache.

[Сравнение A–D, схема и план миграции](B105_CONFIGURATION_PROPOSAL.md). Рекомендован **C: TOML как пользовательский источник + программный адаптер в SQLFluff**, с immutable resolved settings и техническими invariants в коде. Это предложение; `formatter_profiles.toml` и resolver не созданы.

Принципиальные решения для ревью:

- Разрешать только работающие consumers; 120 из .sqlfluff сейчас не лимит Python-layout, 100/adaptive/pack_to_width — будущий B10.6.
- Column AS сейчас preserve, не require. Built-in и UDF не различаются надёжно в CP03; отдельное builtin-only обещание неверно.
- Defaults → profile overrides; строгие типы/enum/unknown-key errors, без cwd/home/SQL-inline настроек и fallback на иной профиль.
- Parser/CP используют один effective snapshot, но разные технические rule overrides; safety не становится пользовательскими переключателями.
- Отдельно согласовать CLI show-config и Python минимум 3.11/целевую 3.12 либо tomli для 3.10. Текущий CLI/adapter не изменён.

## Windows/DBeaver

Автоматизированно проверяются прежние GUI mocks, 1/2/cancel/error, Unicode/BOM/CR, subprocess, merged streams, cwd/чужой config, ошибка чтения/записи/журнала и исходные bytes при отказе. Cold subprocess benchmark запускает официальный adapter.main с headless selector, не подменяет production entry point.

Реальной Windows/VDI и DBeaver здесь нет. Ручная приёмка **не заявлена**. Добавлен [воспроизводимый checklist](../DBEAVER_WINDOWS_SETUP.md#ручная-приёмка-b105-производительность-и-эквивалентность). Полный этап не блокируется отсутствием Windows; GUI/timeout/нагрузка VDI остаются ручной проверкой.

## Изменённые файлы

- `formatter.py`: request boundary; получение value snapshot через внутренний helper без изменения сравнений валидатора.
- `formatter_modules/formatter_case.py`: memo доказанного результата; правила LintFix не менялись.
- `formatter_modules/formatter_request.py`: новый ограниченный request-local механизм для value-only proofs.
- `tests/unit/test_request_proofs.py`: изоляция, lifecycle, ошибки, лимиты, negative validation и repeat.
- `tools/benchmark_formatter.py`, `tools/compare_performance.py`, `tools/profile_formatter.py`, `tools/check_equivalence.py`: воспроизводимые синтетические проверки, без GUI/приватных входов.
- `docs/ROADMAP.md`, `docs/DBEAVER_WINDOWS_SETUP.md`; четыре отчёта B105, каталог JSON, benchmark/phase/equivalence evidence.

Production `.sqlfluff`, grammar, planner, source map, protected scanner, процедурный layout, DBeaver adapter, GUI и golden не изменены. Внутренние реализации валидатора сравнивают те же разрешённые преобразования, новые разрешения не добавлены.

## Оставшийся долг и STOP-GATE

Полная канонизация произвольных ручных LF-переносов, адаптивная ширина, DDL, дальнейшая производительность, ротация trace, lock транзитивных зависимостей и реальная Windows-приёмка остаются отдельными работами. Никакие safety-проверки ради скорости не отключены.

`git diff --check`: PASS. `.sqlfluff`, golden и старые тесты в diff отсутствуют.

**Остановлено перед реализацией Configuration Resolver и миграцией настроек.** B10.6/B11 не начаты. Изменения оставлены для ревью без коммита.

## Повторная проверка перед согласованным коммитом — 23.10.2026

После ревью пользователь разрешил один локальный коммит B10.5a–e; B10.5f не начинается. Проверены все 14 новых файлов: только request-local модуль, его тесты, четыре синтетических инструмента и отчёты/evidence B105. Посторонние файлы, архивы и приватные данные не добавляются.

`python -m pytest tests -q`: **369 passed, 640 subtests passed, 216.88 s**, 0 FAIL/ERROR. Pytest 9.1.1 установлен только во временное тестовое окружение; зависимости проекта не менялись. Запуск pytest без указания `tests` захватывал исторический `docs/archive/test_results.txt` и завершался ошибкой декодирования при collection; архив не является тестовым модулем и не изменялся.

Повторный `tools/check_equivalence.py` подтвердил точное совпадение с сохранёнными результатами базы B10.4: 73 historical ID, 43 входа B10.4 и 4 отказа, включая оба профиля, диагностику и второй проход. `git diff --check`: PASS. Merge, push и deployment не выполняются.
