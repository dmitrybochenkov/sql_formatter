# B9 — Interactive Profile Selector

База B8: d29df0250dcc76c1f10b708eb401b13a3e193028, 291 tests / 0 FAIL / 0 ERROR.
Работа ведётся в feature/b9-profile-selector; master не изменяется.

## Изменения

- `dbeaver_profile_selector.py`: изолированный Tk/ttk UI, импорт Tk только внутри
  select_profile. Клавиши 1/2 (также KP_1/KP_2) немедленно возвращают personal /
  corporate. Esc, крестик или выход event loop без выбора означают отмену.
  Кнопки доступны мышью; нет автоматического профиля по умолчанию.
- `dbeaver_adapter.py`: явная таблица PROFILE_FORMATTERS, оба значения указывают
  на существующую функцию format_bytes B8. Новый select_and_format_bytes вызывается
  только из main после чтения файла и подавления дескрипторов stdout/stderr.
  Не создаётся второй движок. Старый format_bytes остаётся неинтерактивным,
  публичные CLI-аргументы, format_sql и формат External Formatter не изменены.
- `tests/unit/test_profile_selector.py`: GUI-тесты с поддельным event loop, без
  Tk/display; проверены клавиши, отмена, мышь, отказ фокуса и исключения callback.
- `tests/contract/test_contract_b9.py`: выбор маршрута, идентичность профилей,
  отмена/неизвестный профиль/ошибки/неожиданный вывод, B8-валидация, BOM/CRLF,
  последовательные subprocess-запуски и отсутствие GUI у CLI.
- `tests/adapter_runner.py`: только тестовый launcher, подменяет функцию выбора
  до выполнения реального main адаптера в subprocess. Нет production-флага,
  скрытого headless-режима или автоматического выбора при отсутствии Tk.
- `tests/contract/test_contract_b7.py`: прежние проверки сохранены, GUI-граница
  явно подменена Personal; копия проекта включает новый файл селектора.
  Assertions stdout/stderr, кодов, protected bytes и идемпотентности не ослаблены.
- `docs/DBEAVER_WINDOWS_SETUP.md`: подключение Tk, файл для ZIP, таймаут, проверки
  Windows/DBeaver и новые коды журнала.
- `docs/B9_REPORT.md`: этот отчёт.

## Фокус и жизненный цикл

Используются root.lift(), focus_force(), after_idle и кратковременный topmost.
Topmost снимается after(300); при раннем выборе окно уничтожается сразу.
Никаких глобальных keyboard hooks, grab_set_global, AutoHotkey или Win32-хаков.
Отказ focus_force не выбирает профиль: пользователь может кликнуть кнопку.
Ошибки Tk callbacks перехватываются через report_callback_exception, event loop
завершается, окно уничтожается в finally, адаптер возвращает исходные байты.

## Безопасность транспорта

Исходник читается до GUI, поэтому при Esc/крестике/GUI-ошибке возвращается именно
original bytes, включая BOM и окончания строк. Форматирование до выбора не
вызывается. При выборе используется прежний B8 format_bytes с его строгой
валидацией, E004/fallback и protected spans. Весь кандидат готовится до записи
в stdout; новый слой также отвергает неожиданный вывод и неверный тип результата.

Python stdout/stderr внутри выбора и маршрутизации перехватываются; реальные
дескрипторы 1/2 уже заглушены main B7. Только сохранённый stdout-дескриптор
получает итоговые SQL-байты. Поэтому DBeaver может объединять потоки и игнорировать
exit code без добавления в SQL сообщений GUI/диагностики. Отмена и безопасный
fallback имеют код 0 как успешная доставка исходника, по существующей политике.
Чтение/аргументы/неисправный output channel сохраняют прежние коды B7.

Журнал остаётся ограниченным по размеру и best effort: только фиксированные коды,
тип события и выбранный allowlisted ID. Исходный SQL и сообщения исключений не
записываются. ADAPTER-CANCEL/GUI/PROFILE относятся к новому слою. Сбой журнала
не мешает возврату SQL. Обе модели отказа проверены без графической среды.

## Тестирование

Доступная среда: macOS arm64, CPython 3.12.8, SQLFluff 4.4.0.
Реальные Windows/DBeaver B9 и передача фокуса не запускались.
Tk-тесты намеренно не создают графических окон и пригодны для headless CI.

Команды, с PYTHONDONTWRITEBYTECODE=1:

```sh
/tmp/sql_formatter_phase_a/venv/bin/python -m unittest tests.unit.test_profile_selector tests.contract.test_contract_b9 tests.contract.test_contract_b7 tests.regression.test_formatter_b8 -v
/tmp/sql_formatter_phase_a/venv/bin/python -m unittest discover -s tests -t . -p 'test_*.py' -v
```

Целевой финальный прогон: **35 tests / 0 FAIL / 0 ERROR**, 17.228 s.
Полный прогон: **304 tests / 0 FAIL / 0 ERROR**, 224.803 s.
Относительно B8: +13 тестов, FAIL 0 → 0, ERROR 0 → 0.
`git diff d29df02 -- formatter.py formatter_modules .sqlfluff requirements.txt`
пуст: SQL-движок и его настройки побайтно соответствуют B8.

Проверяется реальное выполнение main в subprocess, объединение stderr=STDOUT,
отдельные вызовы Personal/Corporate/Cancel, отсутствие зависимостей (-S),
невалидный SQL, E004, отсутствие Tk, исключение/вывод в GUI, кириллица и пути
с пробелами, BOM/CRLF/CR/mixed из существующей матрицы B7. Функции CLI выполняются
с намеренно заблокированными tkinter и selector: форматирование остаётся рабочим.

SQL-алгоритм B8, formatter.py, formatter_modules, .sqlfluff, requirements,
golden, валидатор и контракт форматирования не менялись. Оба профиля указывают
на один и тот же проверенный callable, а равенство результатов и второй проход
проверяются независимо от маршрутизации. Полный старый набор B7/B8 обязателен.

## Риски и ручная приёмка

DBeaver timeout включает ожидание выбора. Прежние 10000 мс могут быть малы;
в инструкции предложено начать с 120000 мс и проверить значение/единицы на VDI.
При timeout адаптер может быть убит до выдачи SQL; восстановление в таком случае
зависит от DBeaver. Автоматический выбор профиля по таймеру не добавлялся.

[Документация Python Tkinter](https://docs.python.org/3.12/library/tkinter.html)
описывает стандартный модуль и проверку `python -m tkinter`; в корпоративной
урезанной установке Tcl/Tk может отсутствовать. Это приводит к fallback, не к
форматированию без согласия. Зависимости pip не добавлялись.

Проверить на реальном Windows: 1/2/Esc/крестик, фокус/мышь, DPI/несколько мониторов,
несколько последовательных Ctrl+Shift+F, timeout, журнал и побайтный отказ.
Headless-тесты не подтверждают реальную политику foreground-фокуса Windows.
Системные ограничения B7 (непрочитанный файл, разрушенный output channel,
невозможность запуска Python) сохраняются; абсолютная гарантия возврата SQL
при таких внешних отказах не заявляется.

Нужно включить dbeaver_profile_selector.py в переносимую папку/ZIP вместе с
адаптером. Архив не создаётся в этой задаче. После зелёных тестов — отдельный
коммит и push только ветки feature/b9-profile-selector, без merge в master.


## Проверенный пример транспорта

Входные байты: BOM UTF-8 + `select A from T;\r\n`.
Personal и Corporate возвращают одинаковый B8-результат:

```sql
SELECT
    a
FROM t
;
```

Esc/крестик, ошибка GUI и исключение форматтера возвращают исходные байты с
BOM и CRLF; stderr пуст. Проверены два последовательных subprocess-запуска
каждого выбора и независимая идемпотентность форматирования.
