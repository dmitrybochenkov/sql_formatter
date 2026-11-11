# Установка и DBeaver на Windows VDI

Автоматизированные проверки выполнены на macOS, Python 3.10.21 и 3.12.8, SQLFluff 4.4.0: 541 tests / 777 subtests PASS на каждой версии. Реальная Windows/VDI и интерактивный DBeaver пока не приняты. Проверить шаги на копии SQL; [границы гарантий](FORMATTER_CONTRACT.md#интеграция-ошибки-и-диагностика) относятся и к корпоративной среде.

## Python, зависимости и файлы

Проект требует Python >=3.10 (tomli для 3.10, стандартный tomllib начиная с 3.11); проверенные версии — 3.10.21 и 3.12.8, SQLFluff 4.4.0. Для VDI используйте разрешённый IT Python 3.10+ x64 с Tcl/Tk; результаты доступных автоматических прогонов фиксируются в отчёте, фактическая Windows остаётся ручной проверкой. `tkinter` — стандартный модуль, его не устанавливают через pip; при отсутствии Tk нужен согласованный полный Python.

Установить из доверенного ZIP либо Git в доступный каталог, например `C:\Tools\SQL Formatter`. ZIP должен содержать весь проект, включая `config_templates/personal.example.toml`, `formatter.py`, `formatter_modules/`, `dbeaver_adapter.py`, `tools/diagnose_formatter.py`, `requirements.txt`. Для проверки нужны `tests/`. Не переносить macOS `.venv` и `__pycache__`. В актуальной структуре селектор и процедурная грамматика уже внутри `formatter_modules/`; старые корневые wrappers не требуются.

Git-вариант (URL и одобренный commit SHA подставить самостоятельно):

```bat
git clone "<repository-url>" "C:\Tools\SQL Formatter"
git -C "C:\Tools\SQL Formatter" checkout "<approved-commit-sha>"
```

Команды **cmd.exe**, абсолютные пути заменить на реальные:

```bat
"C:\Python312\python.exe" -m venv "C:\Tools\SQL Formatter\.venv"
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m pip install -r "C:\Tools\SQL Formatter\requirements.txt"
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m pip check
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m tkinter
```

Последняя команда должна открыть демонстрационное окно Tk; закрыть его после проверки. Нужны разрешения на запуск Python, создание venv, чтение временных SQL-файлов и запись журналов. Наличие прав администратора или доступа к pip не предполагается.

При отсутствии интернета подготовить wheelhouse на разрешённой Windows-машине с той же Python-версией и архитектурой:

```bat
python -m pip download --only-binary=:all: -r requirements.txt -d wheelhouse
```

Перенести wheelhouse отдельно и установить:

```bat
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m pip install --no-index --find-links="C:\Tools\wheelhouse" -r "C:\Tools\SQL Formatter\requirements.txt"
```

Не подменять версии, если wheel недоступен. `requirements.txt` фиксирует SQLFluff, но не весь транзитивный граф; сохранить `pip freeze` принятой установки для воспроизводимости. После установки сеть и драйвер Teradata форматтеру не нужны.

## Команда External Formatter

В DBeaver найти Preferences → SQL Editor → Formatting → External formatter (названия зависят от установленной версии). Включить передачу через **временный файл**, не stdin. Установить UTF-8 для редактора. Единственная официальная команда:

```text
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\dbeaver_adapter.py" "${file}"
```

Каждый путь и `${file}` заключить в кавычки. Использовать `python.exe`, не `pythonw.exe`; не добавлять shell-перенаправления или активацию venv. Адаптер принимает ровно один аргумент, читает файл и отдаёт SQL в stdout, файл не перезаписывает. Эта команда не менялась при архитектурном переносе модулей.

Для обычных коротких SQL начните с **Exec timeout = 10000 мс**, затем проверьте на VDI. Весь процесс должен укладываться в timeout: запуск Python + таймер селектора (по умолчанию 3 с) + форматирование/валидация + запас. При длительных процедурах измерьте максимум и увеличьте timeout (например, 30000–60000 мс или больше по измерениям). Это рекомендация для ручной проверки, не гарантированный предел.

**3000 мс несовместимы с ожиданием селектора 3 с плюс обработка SQL.** В исследованном [SQLFormatterExternal.java](https://github.com/dbeaver/dbeaver/blob/devel/plugins/org.jkiss.dbeaver.model.sql/src/org/jkiss/dbeaver/model/sql/format/external/SQLFormatterExternal.java) UI проверяет завершение каждые `timeout / 10`: при 120000 мс — раз в 12 с, при 10000 — раз в 1 с. Это объясняет возможную дополнительную задержку при большом timeout, а не ускорение самого Python при уменьшении настройки. Реальная версия DBeaver может отличаться. Настройки не читаются скрыто и не меняются автоматически. При убийстве процесса адаптер не может гарантировать возврат исходника.

Исследованный транспорт DBeaver объединяет stderr/stdout и может использовать вывод при ненулевом exit code: [закреплённая реализация](https://github.com/dbeaver/dbeaver/blob/e97f23bcbd68db782b5300591dc4b61366f30c92/plugins/org.jkiss.dbeaver.model.sql/src/org/jkiss/dbeaver/model/sql/format/external/SQLFormatterExternal.java). Установленная версия может отличаться. Поэтому CLI `formatter.py` и диагностический инструмент **не подключать** вместо адаптера.

## Выбор профиля

Ctrl+Shift+F открывает выбор SQL Formatter только при валидных отличиях Personal от Corporate:

- `1` — Personal, `2` — Corporate, Enter не нужен.
- Esc или крестик — исходные SQL-байты без изменений.
- Если ОС не передала фокус, доступны кнопки мышью.
- Таймер по умолчанию 3 с автоматически выбирает Personal; ручной выбор останавливает его. Esc и крестик отменяют форматирование. Ошибка GUI или отсутствие Tk возвращает исходный SQL.

Оба профиля используют один движок; конфигурация SQLFluff строится программно. При отсутствии, совпадении настроек или ошибке Personal используется Corporate без выбора; отсутствие и удаление файла не вызывают предупреждений. Для валидного Personal отдельного уведомления об изменении нет; ошибка Personal объясняется однократно, при недоступном GUI записывается безопасный код в журнал. [Инструкция настройки](USER_CONFIGURATION.md). GUI изолирован во внутреннем модуле; импорт модулей и CLI не открывают окно. Временный topmost отключается через 300 мс; глобального перехвата клавиатуры нет. Фокус на Windows/VDI не гарантируется headless-тестами.

## Smoke-test установки

Сохранить UTF-8 `C:\Tools\sample.sql`:

```sql
SELECT id, name FROM users WHERE active=1;
```

В cmd.exe:

```bat
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\dbeaver_adapter.py" "C:\Tools\sample.sql" > "C:\Tools\actual.sql"
```

Выбрать 1. Результат:

```sql
SELECT
    id
    , name
FROM users

WHERE active = 1
;
```

Повторить с 2 — тот же результат. Повторить на actual.sql — побайтно тот же SQL. Esc/крестик на исходном sample.sql должны вернуть исходное содержимое. Затем повторить в DBeaver на копии запроса. Не использовать PowerShell-перенаправление, которое может перекодировать вывод, для проверки точных байтов.

Полный тестовый набор из корня проекта, без GUI:

```bat
.venv\Scripts\python.exe -B -m unittest discover -s tests -t . -p "test_*.py" -v
```

CLI для независимой проверки движка, без окна:

```bat
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\formatter.py" "C:\Tools\sample.sql"
```

У CLI диагностика может идти в stderr; это нормальный отдельный интерфейс, не транспорт редактора.

## Диагностика и журналы

Без GUI, с существующей `.venv`:

```bat
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\tools\diagnose_formatter.py" "C:\Private\input.sql" personal "%LOCALAPPDATA%\SQLFormatter\logs\personal"
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\tools\diagnose_formatter.py" "C:\Private\input.sql" corporate "%LOCALAPPDATA%\SQLFormatter\logs\corporate"
```

Этот инструмент **не выводит SQL** и не создаёт его копий. Возвращает 0 при завершённой диагностике, включая безопасный отказ; 1 при ошибке чтения/запуска; 2 при неверных аргументах. Смотреть `diagnostic.jsonl`: read/profile/decode/parse/layout/planner/case/validate/repeat/rollback, коды и elapsed_ms. Позиция `view=candidate` относится к сформированному кандидату, а не исходному файлу. Подробная трасса процедур измеряет вложенные этапы; времена родителей включают дочерние и не суммируются с ними.

Для реального запуска из DBeaver установить окружение **до старта DBeaver**:

```bat
set "SQL_FORMATTER_TRACE=1"
set "SQL_FORMATTER_LOG_DIR=%LOCALAPPDATA%\SQLFormatter\logs"
```

Запустить DBeaver из этого окружения. Уже запущенное приложение переменные не наследует. Для отключения:

```bat
set "SQL_FORMATTER_TRACE="
set "SQL_FORMATTER_LOG_DIR="
```

Перезапустить DBeaver из очищенного окружения. Если переменные заданы в пользовательских настройках Windows, удалить их там тоже. Headless `tools/diagnose_formatter.py` явно включает трассу только в собственном процессе.

По умолчанию журналы находятся в `%LOCALAPPDATA%\SQLFormatter\logs`; если LOCALAPPDATA отсутствует — в системном temp/SQLFormatter/logs. `SQL_FORMATTER_LOG_DIR` меняет каталог. `adapter.jsonl` содержит безопасные коды и категории, выбор профиля/отмену; около 256 KiB переносится в `adapter.previous.jsonl`. `diagnostic.jsonl` включён только явно и **не ротируется** — включать временно, затем архивировать/удалять локально по правилам IT. SQL, пути исходных файлов, объектные имена, литералы, traceback и текст исключений не журналируются. Ошибка записи журнала не влияет на SQL. При параллельной ротации возможна потеря диагностической записи.

## Типовые проблемы и границы доставки

| Симптом | Проверка |
|---|---|
| SQL не меняется | Отмена, ADAPTER-GUI/FORMAT/REFUSAL, C001/E003/E004; запустить headless-диагностику обоих профилей. Для поддержанных процедур B10.3b устранено накопление внешнего DML-отступа. |
| Нет окна | Проверить Tcl/Tk через `-m tkinter`, интерактивную сессию, VDI-фокус и журнал; автоматического профиля нет. |
| Долгое ожидание | Выбор профиля входит в timeout; измерить layout/валидацию/repeat, не отключать защиту. |
| Ошибка импортов после обновления | Перенести полный пакет `formatter_modules/`, проверить venv и `pip check`. Personal и шаблон не нужны для импорта или работы Corporate. |
| Искажения Unicode | UTF-8 редактора/временного файла; не использовать текстовую перекодировку shell. |
| Пустой вывод | Проверить доступ к входу, число аргументов, запуск Python, timeout и выходной pipe на копии SQL. |

Код адаптера 0 означает доставленный SQL, в том числе исходник при отказе. Ошибки аргументов дают 2, чтения/записи/старта — 1. Если файл не прочитан, его bytes вернуть невозможно. После частичной записи в сломанный pipe fallback не дописывается. Ошибки запуска Python, синтаксически повреждённый адаптер, остановка процесса или timeout со стороны DBeaver вне гарантий адаптера; редактор может использовать пустой/неполный вывод. Эти сценарии проверять на копиях, не обещать безусловную защиту от всех сбоев среды.

## Обновление установленной версии

Закрыть DBeaver, сохранить приватные SQL вне каталога проекта. Для ZIP распаковать одобренную полную версию в отдельный каталог и создать Windows-venv заново; не накладывать новый ZIP поверх старого с оставшимися модулями. Для Git проверить `git status`, не перезаписывать локальные изменения, перейти на согласованный commit. Обновить зависимости из requirements, выполнить pip check и smoke-test. При изменении каталога поправить только пути команды DBeaver; интерфейс `adapter.py file` прежний. Ни автоматический pull/merge, ни загрузка приватного SQL на GitHub не требуются.

## Ручная приёмка Windows VDI

- Зафиксировать Windows, Python, DBeaver, разрядность и транзитивные версии зависимостей.
- Проверить AppLocker/EDR, права чтения temp/записи журнала, offline-установку.
- Пути с пробелами/кириллицей, произвольная cwd, отсутствие влияния пользовательского `.sqlfluff`.
- Ctrl+Shift+F → 1/2, Esc/крестик; мышь, DPI/мониторы, фокус и длительное ожидание.
- UTF-8, emoji, BOM, LF/CRLF/CR/mixed, защищённые многострочные значения; повторный проход.
- `SELECT FROM;`, именованное окно OVER w, C001/E002, недоступный журнал: никакой диагностики в редакторе.
- Синтетические процедуры с циклом/INSERT SELECT, затем приватный SQL локально; ни SQL, ни литералы не публиковать в отчётах.
- Недоступный файл/Python, timeout и оборванный вывод — проверить поведение редактора на копии.

Текущие функциональные ограничения и ещё не принятые замечания JOIN/отступов перечислены в [контракте](FORMATTER_CONTRACT.md) и [roadmap](ROADMAP.md).

## Ручная приёмка B10.5: производительность и эквивалентность

Автоматизированные headless-тесты не подтверждают Windows GUI. На целевой VDI:

1. Зафиксировать Python/SQLFluff, версию DBeaver и approved commit; использовать отдельные каталоги baseline B10.4 и candidate, одинаковую версию Python, без переноса macOS venv.
2. На синтетическом sample.sql проверить 1/2, Esc, крестик, mouse fallback и отсутствие автоформатирования при ошибке Tk. Официальная команда External Formatter остаётся прежней.
3. Сравнить результат обеих версий и повторного запуска побайтно; включить Unicode, BOM, CRLF/CR и protected multiline. На отказе проверить точное возвращение исходных bytes; диагностика не должна попасть в редактор.
4. Для замера без GUI запустить из candidate-каталога: `.venv\Scripts\python.exe tools\compare_performance.py --baseline "C:\Tools\Baseline" --candidate "C:\Tools\Candidate" --output performance.json`. Инструмент использует только встроенные синтетические SQL; оба checkout запускаются одним interpreter.
5. Реальный Ctrl+Shift+F измерять отдельно: время выбора профиля не включать в engine benchmark; timeout DBeaver включает диалог и всю проверку процедуры. Не снижать timeout по одному локальному замеру.
6. Повторить из иной cwd и пути с пробелами/кириллицей, с чужим `.sqlfluff`, без доступа к сети, с недоступным журналом. Проверить stdout/stderr и повторные вызовы.
7. Записать median/min/max нескольких чередующихся запусков. При нестабильном времени зафиксировать VDI load; не обещать 5–8 секунд для произвольного SQL.

Приватный SQL не передавать benchmark-инструментам и не добавлять в отчёты/репозиторий. Этот checklist относится к B10.5a–e. В B10.5f runtime-конфигурация перенесена; новые CLI-параметры не добавлялись.

## Ручная приёмка B10.5f

Проверить на VDI: отсутствие локального файла без окна; локальная копия шаблона без окна; удаление без предупреждения; изменение case/commas → только выбор с таймером; повтор → выбор; неверный TOML → одно предупреждение и Corporate; исправление/возврат → без информационного алерта. Проверить Esc, фокус, несколько установок, параллельные Ctrl+Shift+F, права LOCALAPPDATA и lock msvcrt, timeout с единственным окном выбора. Windows не подтверждён автоматическими macOS-тестами.


### Общий код и локальные настройки B10.5f

Код можно разместить в общей сетевой папке. Python и `.venv` остаются локальными у каждого пользователя; в команде DBeaver первый путь указывает на локальный `python.exe`, второй — на общий `dbeaver_adapter.py`. Оба пути заключать в кавычки. Интерфейс внешнего форматтера не меняется. Фактический запуск с UNC/VDI необходимо проверить на рабочей машине.

Personal по умолчанию отсутствует. Для настройки скопируйте `config_templates/personal.example.toml` через Проводник в `%LOCALAPPDATA%\SQLFormatter\personal.toml`; подробные шаги без терминала — [здесь](USER_CONFIGURATION.md). Не редактируйте шаблон в общей папке: он не применяется. Состояние уведомлений локальное, рядом с Personal. Если LOCALAPPDATA отсутствует или относительный, применяется Corporate без fallback и без предупреждения об отсутствии Personal.

Проверьте два разных пользователя: изменения одного не влияют на другого. Также проверьте изменение → ошибка → исправление → удаление, повторный вызов, недоступный локальный каталог, пути с пробелами и msvcrt-lock при параллельных вызовах. Не переносите личный TOML в ZIP исходного проекта.

## B10.6: PowerShell 5.1, Python 3.10 и UTF-8

В локальном каталоге установки/окружения (не создавать venv на общей UNC-папке):

```powershell
py -0p
python --version
py -3.10 -m venv .venv
# Альтернатива при выбранном правильном python.exe:
# python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Необязательная активация:
.\.venv\Scripts\Activate.ps1
```

Если исходники на сетевой папке, передайте полный UNC-путь к requirements.txt.
При запрещённых скриптах активация не нужна: вызывайте python.exe из venv напрямую.
Unix-команды `python3` и `.venv/bin/python` к Windows не относятся.

В DBeaver: **Formatter = External**, **Use temp file = включено**,
**Exec timeout = 10000 ms** для начальной проверки коротких SQL. Команда:

```text
"C:\path\to\sql_formatter\.venv\Scripts\python.exe" "C:\path\to\sql_formatter\dbeaver_adapter.py" "${file}"
```

При общем исходном коде второй путь заменяется UNC-путём; Python/venv локальные.
Без Use temp file адаптер не получает исходные байты, и не может вернуть их
редактору. DBeaver может заменить текст пустым выводом даже при ненулевом exit code.
Это **неподдерживаемая конфигурация**, не используйте её. При штатной передаче
читаемого файла ошибки форматирования возвращают именно исходные байты.
Файл не перезаписывается. Ошибки до чтения или принудительное завершение процесса
не позволяют гарантировать возврат SQL; ручную проверку делайте на копии.

CLI явно выдаёт stdout и stderr в UTF-8, без настройки потоков при импорте.
Для чтения traceback в интерактивной PowerShell 5.1 согласуйте кодировку терминала:

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$OutputEncoding = [Console]::OutputEncoding
$env:PYTHONIOENCODING = 'utf-8'
.\.venv\Scripts\python.exe formatter.py .\sample.sql
```

Не используйте `>`/`Out-File` для побайтной проверки SQL: Windows PowerShell 5.1
может перекодировать результат в UTF-16LE. См. [Microsoft: Character Encoding](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_character_encoding?view=powershell-5.1).
Проверенный автоматическими тестами способ диагностики без зависимости от консоли:

```powershell
.\.venv\Scripts\python.exe tools\diagnose_formatter.py .\sample.sql corporate "$env:LOCALAPPDATA\SQLFormatter\logs"
Get-Content -LiteralPath "$env:LOCALAPPDATA\SQLFormatter\logs\diagnostic.jsonl" -Encoding UTF8
```

Журнал UTF-8 содержит JSON с ASCII-совместимыми кодами, этапом, типом ошибки,
типом сегмента, строкой/позицией/смещением для найденного unparsable. Полный SQL,
имена, литералы и проблемный фрагмент не записываются ради конфиденциальности.
Исключения CLI не подавляются; DBeaver по-прежнему получает только SQL.
Реальная отрисовка PowerShell 5.1, Windows/Tk focus, UNC и конкретная версия
DBeaver требуют ручной приёмки; subprocess-тесты на macOS это не заменяют.
