# B10.6 — текущая проверка

11.11.2026: ветка `feature/b10-6-lists-unicode-windows`, база `74b3f24`. Реализованы явные Personal-режимы IN/VALUES, Unicode identifiers и Windows/UTF-8 инструкции. Corporate-default сохранён. Python 3.10/3.12: 541 tests / 777 subtests PASS; 120 baseline comparisons PASS. Итоги — [B106_REPORT](archive/B106_REPORT.md); ручная Windows-приёмка открыта. Разрешены тематические коммиты и push feature-ветки после проверок, без merge/main. Следующие записи — исторические.

# Текущая проверка: Named Parameters / Selector / Python 3.10

09.11.2026: работа в `feature/b10-5f-user-profiles`, база `0d8ad3e`. Поддержка bind-параметров, единственное окно выбора с таймером Personal, Python 3.10, безопасная parse-диагностика. SQL-правила Corporate сохранены. Полные проверки: Python 3.10.21 и 3.12.8 — по 430 tests / 778 subtests PASS; Corporate equivalence 73 + 43 + 4 PASS. Итог — [отчёт](archive/NAMED_PARAMETERS_SELECTOR_PY310_REPORT.md). После финальной проверки отдельно разрешены один commit и push текущей feature-ветки; merge/rebase/main исключены. Windows VDI требует ручной приёмки. Исторические результаты B10.5f ниже.

# Roadmap

Актуальное состояние B10.5f, 24.10.2026: 413 tests / 743 subtests PASS, включая финальное уточнение локального Personal; изменения готовы к ревью без коммита. База — B10.3d `79334d8`, 335 тестов, 0 FAIL / 0 ERROR. B10.4: 358 tests PASS. B10.5: 369 tests PASS; измерения, эквивалентность и ограничения — в [отчёте](archive/B105_REPORT.md). Статус реализации не означает завершённую ручную приёмку Windows.

## История

| Этап | Фактический результат | Статус |
|---|---|---|
| B2–B5.4 | Атомарные edits, SELECT/FROM/WHERE, комментарии списков, обычные JOIN, HAVING, CTE, множества, OVER и QUALIFY; 251 тест | Implemented в покрытом подмножестве |
| B6 | Карта CRLF/CR ↔ исходные смещения; LF вне protected spans; проектный `.sqlfluff`; 269 тестов | Implemented |
| B7 | Безопасный DBeaver-адаптер, stdout только SQL, локальный журнал; 282 теста | Implemented; Windows не принят |
| B8 | Доказанные CP01–CP05 изменения регистра; 291 тест | Implemented |
| B9 | Tk-селектор Personal/Corporate, отмена, оба профиля одинаковы; 304 теста | Implemented; GUI/VDI требуют ручной проверки |
| B10.1 | Явная процедурная AST-грамматика; 321 тест | Implemented, затем интегрирована |
| B10.2 | Процедурный layout, INSERT SELECT/DELETE, структура и атомарный откат; 345 тестов | Implemented |
| B10.3a | Диагностика отказа реального локального образца: повторное добавление отступа, E003; 351 тест; `83cc0d7` | Завершён |
| B10.3b | Локальная система отступов DML; реальный образец идемпотентен в обоих профилях; 358 тестов; `9659234` | Завершён, сохранён отдельным коммитом |
| B10.3c | Перенос внутренних модулей, один адаптер, консолидация документов без изменения SQL-output | 358/358 тестов и 73 побайтных сравнения PASS; сохранён коммитом `df60328`; подробности в [отчёте](archive/B103C_REPORT.md) |
| B10.3d | Общие fixtures/helpers, разделение регрессий, доказанная дедупликация и аудит comment helper | 335/335 тестов PASS; отчёт и сверка SQL-output — [B103D_REPORT](archive/B103D_REPORT.md); сохранён коммитом `79334d8` |
| B10.4 | Derived JOIN, пробел перед алиасом, нулевой корневой отступ и удаление необязательного табличного AS | 358/358 tests PASS; проверки и ограничения — [B104_REPORT](archive/B104_REPORT.md); сохранён коммитом `c92f310` |
| B10.5a | Performance Baseline & Profiling | Измерены synthetic cold/warm и ABBA; [baseline](archive/B105A_PERFORMANCE_BASELINE.md) |
| B10.5b | Safe Runtime Optimization | Request-local value proofs; без AST/Linter cache и ослабления проверок |
| B10.5c | Performance Regression & Equivalence | Baseline 358/358 и candidate 369/369 PASS; 73 historical + 43 B10.4 + 4 refusal comparisons PASS |
| B10.5d | Windows/DBeaver Acceptance | Автоматизированные проверки PASS, checklist обновлён; Windows не подтверждён |
| B10.5e | Configuration Inventory & Architecture | [Каталог](archive/B105E_CONFIGURATION_INVENTORY.md): 520 записей |
| B10.5f | User Configuration & Automatic Profile Selection | Реализовано после согласования: Corporate/Personal, 5 групп настроек; [отчёт](archive/B105F_REPORT.md), без коммита |
| B10.6 | Configurable IN/VALUES, Unicode, Windows/UTF-8 | Реализовано; явные режимы Personal, Corporate fallback сохранён; [отчёт](archive/B106_REPORT.md) |
| B11 | Поддержка DDL после определения синтаксического охвата и golden | Planned, не начат |

## Открытые работы

1. **Review — B10.5f.** Конфигурация и автоматический выбор готовы к ревью. B10.5a–e сохранён коммитом `cf68fd0`; B10.4 — `c92f310`.
2. **Known issue — произвольные LF-переносы.** Не все семантически одинаковые раскладки приводятся к одному виду. Например, разрывы внутри выражений/IN могут сохраняться; B10.3b устраняет накопление *внешнего* отступа, а не задаёт новый стиль внутренних выражений. Примеры: [B10.3a](archive/B103A_REPORT.md), [B10.3b](archive/B103B_REPORT.md).
3. **Planned — производительность.** Отдельно измерить parse/layout/CP/валидацию/повтор на VDI. Локальные B10.3b вызовы приватного образца занимали около 18–20 с; это не Windows-бенчмарк. Не отключать проверки ради скорости. Повторное создание конфигураций parser/case имеет разные параметры; объединение без доказательства эквивалентности отложено.
4. **Planned — Windows/DBeaver приёмка.** Проверить фокус, Tk, клавиши/отмену, UTF-8/BOM/CR, пути, timeout, разрешения VDI, offline-установку и сценарии недоступного входа/выхода. [Чек-лист](DBEAVER_WINDOWS_SETUP.md#ручная-приёмка-windows-vdi).
5. **Технический долг.** Грамматика привязана к SQLFluff 4.4.0 и его приватному dialect-object hook. Транзитивные зависимости не закреплены lock-файлом. Диагностический JSONL не ротируется; включать временно. Неподдержанные процедуры (IF, handlers/cursors и т. п.) требуют отдельного задания.

## Границы этапов

B10.5 меняет только повторное использование value-only proofs внутри одного запроса. Layout, CP-политики, grammar, planner и DBeaver API сохраняются. На этапе a–e конфигурационная архитектура была только предложена; B10.5f реализует отдельно согласованную схему. Commit/merge/push/deployment не выполняются. После отчёта — ревью; B10.6 и B11 не начинаются.

Актуальные источники: [контракт](FORMATTER_CONTRACT.md), [инструкция](DBEAVER_WINDOWS_SETUP.md). Исторические отчёты и прежние редакции контрактов находятся в `archive/` и не переопределяют текущие статусы.

## B10.5: контрольная точка

База — закоммиченный B10.4 `c92f310`, 358/358 тестов. До оптимизаций снимаются воспроизводимые замеры. Без изменения SQL-output, диагностики, CP и безопасности. Исторический STOP этапов a–e снят согласованием B10.5f: реализуется personal.toml и встроенный Corporate; прежняя иллюстрация formatter_profiles.toml не вводится. Commit/merge/push/deployment не выполняются.

## B10.6: прежнее направление (уточнено заданием 11.11.2026)

Мягкий лимит 100 символов; SELECT/GROUP BY/ORDER BY — ведущие запятые; CALL и аргументы функций — завершающие. IN/VALUES — несколько элементов на строке с упаковкой по ширине; IN (SELECT ...) — правила вложенного запроса. Сохранение допустимых ручных переносов, синтаксически безопасные комментарии/protected spans и идемпотентность обязательны. Задание 11.11.2026 реализует только явные режимы IN/VALUES; остальные скобки и Corporate-default не меняются. Текущий контракт и примеры — в B106_REPORT.

## B10.5f — текущая работа

База `cf68fd0`, 369 tests / 640 subtests PASS. Ветка `feature/b10-5f-user-profiles`: встроенный Corporate, необязательный локальный personal.toml и неактивный config_templates/personal.example.toml, пять групп настроек и автоматический выбор/уведомления. Новый этап заменяет прежний STOP на реализацию resolver, но не разрешает B10.6/B11. Результаты — [B105F_REPORT](archive/B105F_REPORT.md). Commit/merge/push/deployment запрещены до ревью.
