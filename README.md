# Teradata SQL Formatter

Форматирование Teradata SQL и поддерживаемого подмножества процедур на SQLFluff **4.4.0**. Один движок, встроенный Corporate и настраиваемый Personal; начальные настройки совпадают. Personal необязателен: без локального файла используется Corporate. Шаблон `config_templates/personal.example.toml` нужно вручную скопировать в пользовательский каталог по инструкции; из общей папки он не применяется. Литералы, комментарии и quoted identifiers защищены; DBeaver-адаптер возвращает исходные байты при отказе.

- [Личные настройки и автоматический выбор профиля](docs/USER_CONFIGURATION.md)
- [Контракт и известные ограничения](docs/FORMATTER_CONTRACT.md)
- [Установка и подключение к DBeaver на Windows](docs/DBEAVER_WINDOWS_SETUP.md)
- [Roadmap и статус ручной приёмки](docs/ROADMAP.md)

Проверенные автоматизированные среды: Python 3.10.21 и 3.12.8 на macOS; на каждой 541 tests / 777 subtests PASS. Ручная приёмка Windows/VDI остаётся открытой.

## Запуск

Требуется Python 3.10+ (целевая версия 3.12). Создать локальное окружение и установить `requirements.txt`. Windows / PowerShell:

```powershell
py -0p
python --version
py -3.10 -m venv .venv
# Альтернатива: python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe formatter.py input.sql
```

macOS/Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B formatter.py input.sql
```

`formatter.py -h` / `--help` показывают справку. `formatter.py` — headless CLI, SQL в stdout, диагностика в stderr. Для DBeaver использовать **только `dbeaver_adapter.py`**, команду и настройки из инструкции: его stdout содержит SQL, а диагностика идёт в локальный журнал. `tools/diagnose_formatter.py` не выводит SQL и не является адаптером редактора.

## Тесты

В dev-окружении нужен pytest (он не является runtime-зависимостью). Windows: `.\.venv\Scripts\python.exe -m pytest tests -q`. macOS/Linux из корня проекта:

```sh
.venv/bin/python -B -m pytest tests -q
```

Не добавлять приватные SQL-файлы в репозиторий. Исторические отчёты сохранены в `docs/archive/`; актуальные правила находятся в трёх документах выше.

Именованные bind-параметры Teradata `:Calc_Date` распознаются локальным расширением AST и сохраняют исходное написание. При валидных отличиях Personal появляется одно окно: `1` Personal, `2` Corporate; таймер (default 3 с) автоматически выбирает Personal, Esc отменяет. См. [ручную проверку](tests/manual/README.md).

B10.6 добавляет явные Personal-режимы IN/VALUES (`single_line`, `multiline`, `adaptive`) и сохраняет Unicode-идентификаторы. Corporate без новой настройки остаётся прежним. См. [настройки](docs/USER_CONFIGURATION.md) и [Windows/UTF-8](docs/DBEAVER_WINDOWS_SETUP.md).
