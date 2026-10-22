# Teradata SQL Formatter

Форматирование Teradata SQL и поддерживаемого подмножества процедур на SQLFluff **4.4.0**. Один движок, два пока одинаковых профиля Personal/Corporate. Литералы, комментарии и quoted identifiers защищены; DBeaver-адаптер возвращает исходные байты при отказе.

- [Контракт и известные ограничения](docs/FORMATTER_CONTRACT.md)
- [Установка и подключение к DBeaver на Windows](docs/DBEAVER_WINDOWS_SETUP.md)
- [Roadmap и статус ручной приёмки](docs/ROADMAP.md)

Проверенная автоматизированная среда: Python 3.12.8 на macOS. Ручная приёмка Windows/VDI остаётся открытой.

## Запуск

Создать локальное окружение и установить `requirements.txt` (на Windows использовать `.venv\Scripts\python.exe` вместо `.venv/bin/python`):

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -B formatter.py input.sql
```

`formatter.py` — headless CLI, SQL в stdout, диагностика в stderr. Для DBeaver использовать **только `dbeaver_adapter.py`**, команду и настройки из инструкции: его stdout содержит SQL, а диагностика идёт в локальный журнал. `diagnose_formatter.py` не выводит SQL и не является адаптером редактора.

## Тесты

Из корня проекта:

```sh
.venv/bin/python -B -m unittest discover -s tests -t . -p 'test_*.py' -v
```

Не добавлять приватные SQL-файлы в репозиторий. Исторические отчёты сохранены в `docs/archive/`; актуальные правила находятся в трёх документах выше.
