# Установка и DBeaver на Windows VDI

Автоматизированные проверки выполняются на macOS, Python 3.12.8, SQLFluff 4.4.0. Реальная Windows/VDI и интерактивный DBeaver пока не приняты. Проверить шаги на копии SQL; [границы гарантий](FORMATTER_CONTRACT.md#интеграция-ошибки-и-диагностика) относятся и к корпоративной среде.

## Python, зависимости и файлы

SQLFluff 4.4.0 требует Python >=3.10; проверенная версия проекта — 3.12.8. Для VDI кандидат — разрешённый IT Python 3.12 x64 с Tcl/Tk. Другие версии не объявляются протестированными. `tkinter` — стандартный модуль, его не устанавливают через pip; при отсутствии Tk нужен согласованный полный Python.

Установить из доверенного ZIP либо Git в доступный каталог, например `C:\Tools\SQL Formatter`. ZIP должен содержать весь проект, включая скрытый `.sqlfluff`, `formatter.py`, `formatter_modules/`, `dbeaver_adapter.py`, `diagnose_formatter.py`, `requirements.txt`. Для проверки нужны `tests/`. Не переносить macOS `.venv` и `__pycache__`. В актуальной структуре селектор и процедурная грамматика уже внутри `formatter_modules/`; старые корневые wrappers не требуются.

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

Увеличить timeout, например до **120000 мс**, и проверить единицы/поведение в своей версии DBeaver. Timeout включает выбор профиля, форматирование и проверку повторного прохода процедуры. На больших процедурах измерить время на VDI; не считать 120 секунд универсальной гарантией. При убийстве процесса адаптер не может вернуть исходник.

Исследованный транспорт DBeaver объединяет stderr/stdout и может использовать вывод при ненулевом exit code: [закреплённая реализация](https://github.com/dbeaver/dbeaver/blob/e97f23bcbd68db782b5300591dc4b61366f30c92/plugins/org.jkiss.dbeaver.model.sql/src/org/jkiss/dbeaver/model/sql/format/external/SQLFormatterExternal.java). Установленная версия может отличаться. Поэтому CLI `formatter.py` и диагностический инструмент **не подключать** вместо адаптера.

## Выбор профиля

Ctrl+Shift+F открывает SQL Formatter:

- `1` — Personal, `2` — Corporate, Enter не нужен.
- Esc или крестик — исходные SQL-байты без изменений.
- Если ОС не передала фокус, доступны кнопки мышью.
- Ошибка GUI, отсутствие Tk или неизвестный профиль не выбирают стиль автоматически.

Оба профиля сейчас используют один движок и одинаковый `.sqlfluff`. GUI изолирован во внутреннем модуле; импорт модулей и CLI не открывают окно. Временный topmost отключается через 300 мс; глобального перехвата клавиатуры нет. Фокус на Windows/VDI не гарантируется headless-тестами.

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
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\diagnose_formatter.py" "C:\Private\input.sql" personal "%LOCALAPPDATA%\SQLFormatter\logs\personal"
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "C:\Tools\SQL Formatter\diagnose_formatter.py" "C:\Private\input.sql" corporate "%LOCALAPPDATA%\SQLFormatter\logs\corporate"
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

Перезапустить DBeaver из очищенного окружения. Если переменные заданы в пользовательских настройках Windows, удалить их там тоже. Headless `diagnose_formatter.py` явно включает трассу только в собственном процессе.

По умолчанию журналы находятся в `%LOCALAPPDATA%\SQLFormatter\logs`; если LOCALAPPDATA отсутствует — в системном temp/SQLFormatter/logs. `SQL_FORMATTER_LOG_DIR` меняет каталог. `adapter.jsonl` содержит безопасные коды и категории, выбор профиля/отмену; около 256 KiB переносится в `adapter.previous.jsonl`. `diagnostic.jsonl` включён только явно и **не ротируется** — включать временно, затем архивировать/удалять локально по правилам IT. SQL, пути исходных файлов, объектные имена, литералы, traceback и текст исключений не журналируются. Ошибка записи журнала не влияет на SQL. При параллельной ротации возможна потеря диагностической записи.

## Типовые проблемы и границы доставки

| Симптом | Проверка |
|---|---|
| SQL не меняется | Отмена, ADAPTER-GUI/FORMAT/REFUSAL, C001/E003/E004; запустить headless-диагностику обоих профилей. Для поддержанных процедур B10.3b устранено накопление внешнего DML-отступа. |
| Нет окна | Проверить Tcl/Tk через `-m tkinter`, интерактивную сессию, VDI-фокус и журнал; автоматического профиля нет. |
| Долгое ожидание | Выбор профиля входит в timeout; измерить layout/валидацию/repeat, не отключать защиту. |
| Ошибка импортов после обновления | Перенести полный пакет `formatter_modules/`, `.sqlfluff`, проверить venv и `pip check`. |
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
