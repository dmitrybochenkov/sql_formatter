# B10.5f — User Configuration, Corporate Profile & Automatic Profile Selection

## База и границы

База: `cf68fd0621af857ad476ccb6225ffcea0dc7a662`, чистая ветка `feature/b10-5-performance-config`. Создана отдельная `feature/b10-5f-user-profiles`. B10.5a–e: 369 tests / 640 subtests PASS. Повторная исходная проверка: `python -m pytest tests -q` — 369 passed, 640 subtests passed, 230.52 s. Среда: macOS, Python 3.12.8, SQLFluff 4.4.0; pytest 9.1.1 во временном тестовом окружении.

Пользователь отдельно согласовал исключение `group_by.layout="multiline"`: один элемент всегда остаётся рядом с заголовком; два и более форматируются построчно. Этот контракт отражён в Personal, документации и regression-тесте.

Реальные корпоративные SQL и приватные файлы не использованы. Ничего не закоммичено, не слито, не опубликовано. B10.6 и B11 не выполнялись.

## Архитектура

- `formatter_config.py`: строгая TOML-схема, отдельные versioned Personal defaults, frozen Settings, сравнение нормализованных значений, scoped immutable snapshot.
- `corporate_profile.py`: полный встроенный Corporate, без чтения Personal и его overrides.
- `sqlfluff_config_adapter.py`: программный FluffConfig, без cwd/home/project-file discovery. Parser и CP получают разные технические настройки; Teradata 4.4.0/raw/120 сохранены. `.sqlfluff` остаётся в репозитории для исторического/ручного использования, runtime его не читает.
- CP01–CP05: upper/lower допускаются только по конкретному LintFix, с прежними проверками leaf, длины, типа и AST-принадлежности. Preserve исключает соответствующее правило. Произвольная смена текста токенов не разрешена.
- `profile_layout.py`: дополнительные узкие AST gap-edits для нестандартных comma/spacing/GROUP настроек. Стандартные значения обходят этот проход без дополнительного parse. Оконные списки пропускаются; функции/CALL/IN/VALUES не становятся внешними списками. Группы правок атомарны, planner B2 не изменён. GROUP preserve сопоставляет исходные и результирующие AST-списки, проверяет число элементов.
- WHERE: настройка запрещает создание нового префикса в соответствующей области; HAVING не меняется. Валидатор при false тоже не разрешает новую вставку WHERE. Синтетический AND допускает выбранный lower после CP; сохранены точные остальные токены, области и ограничения eligibility.
- `formatter_request.py`: ключ value-proof включает точный SQL и fingerprint эффективной политики. Нет переноса доказательств между профилями. Жизненный цикл/лимиты/defensive copy и независимый повтор процедуры сохранены.
- DBeaver читает Personal один раз на вызов. Снимок выбранного профиля сохраняется на весь вызов, даже если файл изменён во время диалога. Headless прямые profile routes изолированы от другого текущего профиля. `formatter.py [path]` по-прежнему использует Corporate без GUI.

## Параметры и реальные результаты

Все пять групп реализованы: CP case upper/lower/preserve; независимые leading/trailing SELECT/FROM/GROUP/ORDER; семь spacing boundaries; WHERE true/false; GROUP multiline/inline/preserve.

Один элемент GROUP при multiline: `GROUP BY a`, даже для входа `GROUP BY\n a`. Preserve хранит наличие переносов между элементами и после заголовка, а не произвольное количество пустых строк/пробелов. На горизонтальной границе разделитель `, `; на вертикальной — выбранная comma policy. Inline не удаляет защищённые переносы и не склеивает строковый комментарий со следующим элементом. Неоднозначные comment gaps сохраняются с C001, без частичной группы.

Вход:

```sql
select A,B from T where A=1 and B=2 group by A,B order by A,B;
```

Corporate / локальная копия шаблона Personal (без изменений относительно базы):

```sql
SELECT
    a
    , b
FROM t

WHERE 1=1
    AND a = 1
    AND b = 2

GROUP BY
    a
    , b

ORDER BY
    a
    , b
;
```

Personal: keywords=lower, commas.select=trailing, spacing=[], WHERE=false, GROUP=inline (остальные значения стандартные):

```sql
select
    a,
    b
from t
where a = 1
    and b = 2
group by a, b
order by
    a
    , b
;
```

Оба результата побайтно идемпотентны и проходят strict validation в соответствующем policy scope. Preserve регистра относится к исходным токенам; новый служебный AND не имел исходного написания и создаётся uppercase, затем нормализуется при lower.

## Автовыбор и уведомления

Отсутствующий/удалённый Personal → Corporate без предупреждения и автосоздания. Валидный одинаковый Personal → Corporate без окна. Валидный отличающийся → прежний выбор 1/2/Esc/крестик. Невалидный/недоступный → Corporate без выбора и понятное уведомление. Ошибка окна выбора возвращает исходный SQL. При недоступной GUI-диагностике состояние не отмечается доставленным; Corporate для invalid/identical остаётся доступен без GUI, а различающийся профиль требует явного выбора.

Сравнение использует только пять групп, без SQLFluff initialization. Порядок списка spacing нормализуется. Отдельный SHA-256 отслеживает байтовые изменения файла, включая комментарии. Первое обнаружение любого валидного файла с одинаковыми эффективными значениями не уведомляет; хеш сохраняется для отслеживания последующих изменений. После изменения/исправления/возврата показывается одно сообщение; при необходимости — затем выбор. Новый Corporate fingerprint пересчитывает статус независимо от Personal hash.

`%LOCALAPPDATA%\SQLFormatter\profile_state.json` содержит только версию состояния, хеш локального пути Personal, хеш Personal и fingerprint Corporate. Доставка фиксируется после успешного сообщения; начальное identical-состояние запоминается молча, удаление молча очищает запись. Запись через temp + fsync + atomic replace. Kernel lock предотвращает конкурентные уведомления; занятый lock откладывает сообщение, не SQL. POSIX ветвь протестирована потоками и отдельными процессами; Windows msvcrt требует реальной VDI-проверки. При отсутствии/недоступности каталога состояние не сохраняется, поэтому сообщения могут повторяться. SQL, содержимое TOML и тексты исключений в журнал не попадают.

## Тесты и эквивалентность

Итоговый полный прогон после final adjustment: **413 passed, 743 subtests passed, 242.72 s**, 0 FAIL / 0 ERROR. Относительно базы B10.5a–e (369/640): +44 теста, +103 subtests; относительно предыдущего B10.5f (403/743): +10 тестов. `git diff --check`: PASS.

До финального уточнения о локальном файле: `python -m pytest tests -q` — **403 passed, 743 subtests passed, 388.72 s**, 0 FAIL/ERROR. Целевой набор конфигурации/уведомлений/layout — 31 passed / 103 subtests; дополнительно fake-Tk и вложенный comment-indent — 6 passed / 8 subtests. Проверены независимые смешанные CP-политики (preserve keywords/types + lower functions/literals + upper identifiers), strict validation и повтор.

Полный прогон не является парным performance benchmark: в части времени параллельно выполнялась функциональная equivalence-проверка. Производительность измеряется отдельно после завершения тестов.

[Матрица эквивалентности](B105F_EQUIVALENCE.json): 73 historical ID, 43 уникальных B10.4 input, 4 failure scenarios — точное совпадение с B10.5a–e. Проверены первый/второй output, оба профиля, диагностические коды и strict validation. Старые SQL golden не менялись.

Существующие adapter-тесты адаптированы адресно: выбор/отмена тестируются после смоделированного valid+difference, вместо устаревшего безусловного окна; проверка тождества двух function objects заменена проверкой явных profile IDs, проверки SQL-output и safety сохранены. Fixture установки не требует Personal или шаблона для работы Corporate. Diagnostic test вызывает новый tools-путь. Новые GUI-тесты полностью headless; один пропущенный mock во время разработки был исправлен после native Tk abort в среде без графического сеанса. Это не подтверждение фактической Windows GUI-совместимости.

Запуск pytest без `tests` по-прежнему захватывает исторический `docs/archive/test_results.txt` и падает на collection/кодировке; проблема зафиксирована, архив и pytest discovery вне объёма не исправлялись.

## Перенос диагностики и аудит корня

`diagnose_formatter.py` перенесён в `tools/diagnose_formatter.py`; явно добавлен корень относительно модуля, сохранены три аргумента, оба профиля, тишина stdout/stderr и metadata-only trace. Команда DBeaver не изменена. Проверки вызывают инструмент из другой cwd и путей с пробелами/кириллицей.

В корне найден `sql_formatter.zip`: 157004 bytes, untracked, 118 членов. Безопасно прочитан ZIP directory; абсолютных/родительских traversal paths не обнаружено. Один настоящий SQL-member совпадает по SHA-256 с локальным синтетическим sample; второй `.sql` member — AppleDouble metadata. Есть `__MACOSX` resource forks. Имена, указывающие на приватный образец/журналы/.env, не обнаружены; это не сертификат отсутствия любых персональных метаданных. По структуре — прежний снимок поставки; ссылок на это конкретное имя в актуальных скриптах/инструкциях нет.

ZIP не удалён, не изменён, не добавлен в Git. Для будущего release рекомендуется генерировать чистый артефакт из утверждённого tracked дерева за пределами корня (например, artifacts/ локально), без `__MACOSX`, cache, venv, журналов и приватных SQL. Генерация release в B10.5f не выполнялась. `.DS_Store` и cache-каталоги не включены в изменения, агрессивной уборки не было.

## Ограничения

- Реальная Windows/VDI, фокус Tk, msvcrt lock и DBeaver timeout не проверены; checklist обновлён. Native process crash/kill и оборванный канал остаются вне Python fail-safe гарантии, как в B7.
- На Windows без абсолютного LOCALAPPDATA работает Corporate; если локальный каталог существует, но запись состояния недоступна, уведомления могут повторяться. Во время конкурирующего окна сообщение откладывается до следующего вызова.
- Сохраняются прежние ограничения неподдерживаемых AST, произвольных ручных LF-переносов и неоднозначных комментариев. Раскладка не требует unsafe переписывания таких фрагментов ради настройки.
- Нет adaptive width, DDL, новых CALL/IN/VALUES правил, GUI-редактора или новых CLI-флагов. Пользовательская инструкция не требует терминала.

## Performance comparison

[Исходные samples/min/max/median](B105F_PERFORMANCE.json). Baseline — отдельное дерево из git archive cf68fd0, candidate — B10.5f до финального изменения расположения Personal; один interpreter, синтетический SQL. Чередование B/O/O/B × 2, четыре warm samples каждой версии; cold — три отдельных процесса. Замеры выполнялись после тестов, а не вместе с ними. GUI в адаптере подменён; время пользователя/реального Tk не включено.

| Сценарий | B10.5a–e median, s | B10.5f median, s |
|---|---:|---:|
| Short SELECT | 0.1870 | 0.1918 |
| INSERT | 0.6009 | 0.5949 |
| Large procedure | 5.9286 | 6.1522 |
| Varied procedure | 8.4281 | 8.1401 |
| Cold import | 0.6557 | 0.6495 |
| Cold CLI | 1.1266 | 1.0803 |
| Cold adapter | 1.2696 | 1.0980 |

Большая процедура: baseline min/max 5.7986–6.2426, candidate 5.7589–7.1514 s. Результаты перекрываются; не делается вывод об устойчивом ускорении/замедлении. Hash и диагностика warm/cold результатов совпали. Полный runtime повтор процедуры и строгие проверки сохранены.

Отдельно `tools/benchmark_profile_selection.py`, по три последовательных adapter-вызова:

| Состояние | Median, s | Уведомлений / выборов за 3 вызова |
|---|---:|---:|
| Personal без изменений | 0.2489 | 0 / 0 |
| Изменены комментарии, стиль совпадает | 0.2584 | 3 / 0 |
| На каждом вызове новый hash и отличие; выбран Corporate | 0.2515 | 3 / 3 |
| На каждом вызове новый невалидный hash | 0.2604 | 3 / 0 |

Чтение/валидация/сравнение конфигурации без SQLFluff: 50 samples, median **0.0572 ms**. В changed-сценариях файл меняется перед каждым вызовом; однократность неизменённого состояния отдельно проверена тестами. Используются только временные synthetic Personal/state, production personal.toml не меняется. Все SQL-результаты в этой матрице совпали с Corporate. Эти headless-замеры не являются обещанием задержки реального Ctrl+Shift+F на VDI.

Воспроизведение: `python tools/compare_performance.py --baseline <baseline-dir> --candidate <candidate-dir> --output <json>` и `python tools/benchmark_profile_selection.py --root <candidate-dir> --output <json>`. Не использовать приватный SQL: оба инструмента содержат встроенные синтетические inputs.

## Финальный контроль

`git diff --check`: PASS. Старые golden/fixtures, planner/protected spans/source map и grammar не изменены. HEAD остаётся cf68fd0, ветка feature/b10-5f-user-profiles, изменения не staged и не закоммичены. Новый отчёт и evidence предназначены для ревью; B10.6/B11 не начаты.

## Список изменённых файлов

- `README.md` — изменён.
- `dbeaver_adapter.py` — изменён.
- `diagnose_formatter.py` — удалён из корня, перенесён в tools/.
- `docs/DBEAVER_WINDOWS_SETUP.md` — изменён.
- `docs/FORMATTER_CONTRACT.md` — изменён.
- `docs/ROADMAP.md` — изменён.
- `docs/USER_CONFIGURATION.md` — новый.
- `docs/archive/B105F_EQUIVALENCE.json` — новый.
- `docs/archive/B105F_PERFORMANCE.json` — новый.
- `docs/archive/B105F_REPORT.md` — новый.
- `formatter.py` — изменён.
- `formatter_modules/corporate_profile.py` — новый.
- `formatter_modules/formatter_case.py` — изменён.
- `formatter_modules/formatter_clause_gaps.py` — изменён.
- `formatter_modules/formatter_config.py` — новый.
- `formatter_modules/formatter_request.py` — изменён.
- `formatter_modules/formatter_runtime.py` — изменён.
- `formatter_modules/profile_layout.py` — новый.
- `formatter_modules/profile_notifications.py` — новый.
- `formatter_modules/profile_selector.py` — изменён.
- `formatter_modules/sqlfluff_config_adapter.py` — новый.
- `config_templates/personal.example.toml` — новый неактивный шаблон вместо корневого Personal.
- `tests/contract/test_optional_personal.py` — новый.
- `tests/contract/test_adapter_profiles.py` — изменён.
- `tests/contract/test_diagnostics.py` — изменён.
- `tests/contract/test_procedure_transport.py` — изменён.
- `tests/contract/test_user_profiles.py` — новый.
- `tests/helpers/runners.py` — изменён.
- `tests/regression/test_profile_layout.py` — новый.
- `tests/unit/test_profile_selector.py` — изменён.
- `tests/unit/test_user_configuration.py` — новый.
- `tools/benchmark_profile_selection.py` — новый.
- `tools/diagnose_formatter.py` — новый.


## Final adjustment: optional local Personal

Активный файл Windows: `%LOCALAPPDATA%\SQLFormatter\personal.toml`. macOS: `~/Library/Application Support/SQLFormatter/personal.toml`. Linux: абсолютный `$XDG_CONFIG_HOME/SQLFormatter/personal.toml`, иначе `~/.config/SQLFormatter/personal.toml`. Windows без абсолютного LOCALAPPDATA использует Corporate; общий проект, cwd, `.venv` и родители не просматриваются. `profile_state.json` хранится в том же пользовательском каталоге; идентичность общей установки/UNC не участвует в resolver.

Шаблон перенесён в `config_templates/personal.example.toml`; runtime не читает его и не создаёт рабочий файл автоматически. Документация описывает копирование через Проводник без терминала. Правила форматирования SQL, snapshot, CP и planner не изменены этим уточнением. Прямой headless Personal при отсутствующем файле тоже использует Corporate.

Переходы протестированы: отсутствие→отсутствие (без state и GUI), отсутствие→валидный identical (без GUI, запоминается хеш), валидный differing/изменённый (одно уведомление, затем выбор), невалидный (одно предупреждение + Corporate), исправленный (новое уведомление), удалённый (без предупреждения, запись очищается), повторно созданный. Неизвестные имена ключей/значения TOML не включаются в сообщения. Неизменяемый snapshot при редактировании во время выбора сохраняется.

Дополнительно проверены два пользовательских каталога, Windows drive/path semantics, отсутствующий LOCALAPPDATA, macOS/Linux/XDG, запуск из другой cwd, UNC-подобный путь модуля и неактивность общего шаблона. Это моделирование путей, не фактический сетевой запуск Windows. Добавлен `tests/contract/test_optional_personal.py`; остальные адресные изменения — resolver, notifications, adapter, шаблон, тестовые fixtures, benchmark resolver injection и документация. Финальные результаты полного прогона приводятся ниже.

Повторная матрица после изменения расположения: 73 historical ID + 43 B10.4 input + 4 отказа побайтно совпадают с ранее сохранённым baseline (включая оба прохода, профили и диагностику). `B105F_EQUIVALENCE.json` дополнен отметкой optional-local проверки.


### Итоговые проверки final adjustment

- `PYTHONDONTWRITEBYTECODE=1 /tmp/sql_formatter_b103_venv/bin/python -m pytest tests -q`: **413 passed, 743 subtests passed in 242.72s**, exit 0.
- Целевой набор optional/user profiles + configuration: **30 passed, 87 subtests passed**, 7.27 s.
- Прерванный по команде пользователя прогон (299 passed / 584 subtests, exit 2) не учитывается как полный; после возобновления выполнен новый полный прогон с нуля.
- `git diff --check`: PASS. Изменений golden/fixtures от final adjustment нет. Проверки strict validator, побайтной идемпотентности, protected spans и snapshot остаются зелёными.
- Ветка `feature/b10-5f-user-profiles`, HEAD `cf68fd0621af857ad476ccb6225ffcea0dc7a662`. Изменения сохранены для ревью, без commit/merge/push/deployment.

После полного pytest отдельно выполнен `tools/benchmark_profile_selection.py --root . --output /tmp/b105f-local-selection-performance.json`, три повтора каждого сценария, только временные synthetic Personal/state и mocked GUI. Свежие результаты сохранены в `B105F_PERFORMANCE.json` → `optional_local_selection`:

| Сценарий | Median, s | Уведомления / выборы за 3 вызова |
|---|---:|---:|
| Personal отсутствует | 0.1542 | 0 / 0 |
| Валидный identical без изменений | 0.1644 | 0 / 0 |
| Меняется файл, эффективные настройки identical | 0.1561 | 3 / 0 |
| Меняются отличающиеся настройки, выбран Corporate | 0.1650 | 3 / 3 |
| Меняется невалидный файл | 0.1626 | 3 / 0 |

Configuration-only: 50 samples, median **0.0463 ms**. SQL-output одинаков во всех пяти сценариях. В changed-сценариях перед каждым вызовом новый хеш, поэтому три уведомления ожидаемы; повтор неизменённого состояния проверен тестами. Предыдущие замеры до final adjustment сохранены отдельно: эти серии не являются чередующимся A/B измерением и не доказывают ускорение. Реальные задержки сети/VDI/Tk этим локальным headless-замером не измерялись.
