# Manual Windows / DBeaver acceptance

Эти проверки требуют реальной Windows VDI и установленного DBeaver. Headless-тесты на macOS не подтверждают фокус окна, сетевой запуск или поведение конкретной версии DBeaver. Используйте только синтетический SQL из `tests/manual/input.sql`.

## Установка и версия

1. Проверьте `"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" --version`: поддерживается Python 3.10+.
2. Установите зависимости именно в это локальное окружение: `"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m pip install -r "\\server\share\SQL Formatter\requirements.txt"`. В offline VDI используйте согласованный wheelhouse и `--no-index --find-links`; не заменяйте версии пакетов произвольно.
3. Выполните `"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -m pip check`.
4. Проверьте `"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" "\\server\share\SQL Formatter\formatter.py" --help`: справка, без чтения SQL или GUI.
5. В DBeaver сохраните существующий External Formatter transport (UTF-8, Use temp file). Команда: `"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "\\server\share\SQL Formatter\dbeaver_adapter.py" "${file}"`. Пути примерные, замените на согласованные IT.

## SQL и профили

1. Без локального `%LOCALAPPDATA%\SQLFormatter\personal.toml` Ctrl+Shift+F сразу применяет Corporate, без окна. Предварительно сохраните имеющийся личный файл в безопасном локальном месте, если он существует.
2. В редакторе выполните минимальный пример: `select id from events where report_date=:Calc_Date and id is not null;`. Ожидаются SELECT/FROM/WHERE на контрактных границах, WHERE 1=1 для двух прямых AND; `:Calc_Date` не меняет регистр.
3. Откройте `tests/manual/input.sql` — сложный synthetic CTE/UNION/OVER/вложенный SELECT. Форматирование должно изменить раскладку, сохранив параметры и комментарии. Второй проход побайтно совпадает с первым.
4. Через Проводник скопируйте `config_templates/personal.example.toml` в локальный каталог SQLFormatter под именем `personal.toml`. Без изменений SQL-настроек селектор не появляется. Изменение только timeout также не включает выбор.
5. Установите в локальной копии `[case] keywords = "lower"`. На каждом вызове теперь появляется одно окно выбора без отдельного информационного OK-алерта. Проверьте `1` → Personal (lowercase keywords), `2` → Corporate (uppercase keywords).
6. Ничего не нажимайте: countdown 3→2→1, затем Personal. Установите timeout_seconds=5 и повторите; Enter не нужен. Ручной выбор останавливает таймер. Если фокус не получен, работают кнопки мышью.
7. Esc и крестик оставляют исходные SQL-байты неизменными. Повторите на BOM/CRLF и комментариях. Нажатие `2` около конца отсчёта не должно запускать два форматирования.
8. Проверьте невалидный TOML и timeout_seconds=0: однократное предупреждение об ошибке, затем Corporate; не путать с удалённым уведомлением о валидных отличиях. Исправьте файл — без информационного алерта. Удалите Personal — Corporate без предупреждения.
9. Настоящий parse error (`SELECT id FROM events WHERE id=:;`) и неподдерживаемое именованное окно должны вернуть исходный SQL. Диагностический текст не должен попадать в редактор.
10. Повторите поддерживаемую процедуру с несколькими INSERT/DELETE, Unicode-пути, смешанные окончания строк и multiline protected content. Подробные прежние проверки транспорта остаются в [инструкции](../../docs/DBEAVER_WINDOWS_SETUP.md).

## Время и диагностика

Начальная рекомендация для коротких SQL — Exec timeout **10000 ms**, затем подбор по реальным замерам: запуск + ожидание селектора + форматирование/валидация + запас. 3000 ms недостаточно при таймере 3 секунды. Для больших процедур может понадобиться 30000–60000 ms или больше. В исследованной реализации DBeaver проверка готовности выполняется через timeout/10: большое значение может добавлять задержку даже для быстрого процесса. Не меняйте настройки автоматически и не считайте это подтверждением поведения вашей версии.

Для безопасного opt-in trace используйте существующий инструмент:

```bat
"C:\Tools\SQL Formatter\.venv\Scripts\python.exe" -B "\\server\share\SQL Formatter\tools\diagnose_formatter.py" "C:\Temp\synthetic.sql" corporate "%LOCALAPPDATA%\SQLFormatter\logs\synthetic"
```

`C:\Temp\synthetic.sql` — локальная копия `tests/manual/input.sql`; не сохраняйте приватные образцы в репозитории. Для проверки Personal замените только аргумент профиля. Инструмент headless, stdout/stderr пусты; trace содержит этап/код/type/позицию AST и elapsed_ms, без SQL, имён, значений и путей. Для parse error координата указывает начало `unparsable`-сегмента, а не обязательно отдельный ошибочный символ. Включение trace не меняет rollback.

Зафиксируйте версии Python/SQLFluff/DBeaver, профиль, timeout, elapsed и PASS/FAIL. Отдельно измерьте время CLI, headless диагностики и Ctrl+Shift+F с таймером. Реальный SQL и персональные пути в отчёт не включайте.
