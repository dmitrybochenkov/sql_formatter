# B10.5e — Configuration inventory

Источник: B10.4 `c92f310`, SQLFluff 4.4.0. Аудит не изменяет значения и не вводит новый resolver. Шесть внутренних параметров request-local оптимизации B10.5 добавлены в каталог отдельно; они не пользовательские style settings.

## Полный каталог

Машиночитаемый [каталог](B105_CONFIGURATION_INVENTORY.json) содержит **520 записей** с полями Name, Source, Current value, Type, Allowed values, Scope, Category, Consumer, Public?, Proposed name, Migration, Risk. Включены все скалярные effective-настройки parser и CP-config (в том числе унаследованные defaults SQLFluff), а также все Python-аргументы с defaults. `dialect_obj`/`templater_obj` — производные runtime-объекты, не пользовательские настройки; их selector и версия описаны отдельно. Строки `argument.*` — внутренние API, а не предлагаемые пользовательские переключатели. Параметры не запускаемых правил SQLFluff отмечены отдельно и не должны попасть в новую публичную схему.

Настройки SQLFluff прочитаны из реальных FluffConfig; это effective dump, а не список только ключей `.sqlfluff`. Для rule-параметров с публичным SQLFluff ConfigInfo Allowed values содержит реальные validation enums закреплённой версии; прочие непубличные defaults делегированы схеме SQLFluff; это не обещание поддержки произвольных значений нашим renderer. Значения Python-правил ниже описывают действующий контракт, не вновь утверждённые опции.

## Python, транспорт и инварианты

| Name | Источник | Текущее значение | Класс | Предлагаемое имя / миграция |
|---|---|---|---|---|
| indent | formatter.py:INDENT; formatter_{clause_gaps,list_gaps,comment_lists,lists,procedure} | 4 | style | layout.indent_size; Единый resolver после согласования; заменить все +4/литералы согласованно |
| select.commas | formatter_list_gaps.select_gap_edits | leading | style | layout.select_comma_style; Сохранить leading |
| group_order.commas | formatter_clause_gaps.commented_clause_gap_edits | leading | style | layout.group_by/order_by_comma_style; Сохранить leading |
| from.commas | formatter_clause_gaps.nested_query_gap_edits | leading +4 | style | layout.from_comma_style; Сохранить первый FROM на строке |
| procedure.parameters_call.commas | formatter_procedure.items | leading | style | layout.procedure_parameter/call_comma_style; CALL trailing только B10.6, сейчас leading |
| function.arguments | formatter_clause_gaps / opaque expression spans | preserve existing | style | layout.function_layout; B10.6 отдельно; сейчас не adaptive |
| in_values.layout | formatter_clause_gaps / opaque expression spans | preserve existing | style | layout.in_list_layout; Не добавлять pack_to_width до B10.6 |
| list.single_item | formatter_lists.normalize_simple_list | GROUP/ORDER inline; SELECT newline | style | layout.single_item; Сохранить существующие ветви |
| clause.blank_lines | formatter_clause_gaps.nested_query_gap_edits | one before WHERE/GROUP/HAVING/ORDER/QUALIFY/JOIN; none SELECT–FROM/JOIN–ON | style | layout.clause_spacing; Сохранить exclusions |
| operators.spacing | formatter_clause_gaps / formatter_procedure.operators | one space for supported comparisons | style | layout.operator_spacing; Не менять выражения |
| on.indent | formatter_clause_gaps.render_joins | same as JOIN; direct AND +4 | style | layout.on_indent; Сохранить |
| root.margin | formatter_clause_gaps.statement_margin_edits | 0 | style | layout.root_indent; Сохранить AST root scope |
| derived.alias_gap | formatter_clause_gaps.table_alias_gap_edits | one space | style | layout.alias_gap; Только доказанный AST |
| table_alias_as | formatter_clause_gaps.table_alias_parts | remove if proven optional | style | aliases.table_as; Синхронно renderer + validator |
| column_alias_as | formatter.py validator | preserve | safety | aliases.column_as; НЕ require: вставка AS сейчас запрещена |
| where_having_prefix | formatter_clause_gaps + formatter.validate_sql_unchanged | only >=2 direct AND, no top OR, at most one | safety | None; Сохранить неизменным, не пользовательский toggle |
| on_qualify_prefix | formatter_clause_gaps + validator | never insert 1=1 | safety | None; Сохранить |
| nested_context | formatter_clause_gaps.nested_query_gap_edits | AST depth, +4 | runtime | None; Не превращать feature ownership в профильный флаг |
| procedure.spacing | formatter_procedure.body_units | same-kind DECLARE/SET adjacent; otherwise blank line | style | layout.procedure_spacing; Сохранить |
| semicolon | formatter.format_semicolons / formatter_procedure | SQL own line; procedural attached; terminal LF | style | layout.semicolon; Сохранить обе области |
| external_newlines | formatter_runtime.normalize_external_newlines | LF outside protected; mixed inside | safety | None; Не менять B6 |
| bom | formatter_dialect.decode_sql_bytes | success plain SQL drops BOM, procedure keeps; refusal preserves bytes | runtime | None; Сохранить transport policy |
| protected | formatter_protection.protected_spans | quotes, doubled escapes, line/block comments; unfinished to EOF | safety | None; Никаких отключений |
| ambiguous_comments | formatter_protection.ambiguous_comment_spans / list helpers | blank-line separation -> C001; no guessing mixed chains | safety | None; Сохранить |
| planner.priority | formatter_edits.plan_edits | shortest span then offset; stable ties | safety | None; Не настраивать |
| planner.groups | formatter_edits.plan_edits | all-or-nothing per group; protected/overlap reject | safety | None; Не настраивать |
| legacy.diff | formatter_guarded_pass.guarded_pass | SequenceMatcher autojunk=False | runtime | None; Не менять без equivalent proof |
| validator | formatter.validate_sql_unchanged | exact tokens+ownership+protected; narrow CP/prefix/AS exceptions | safety | None; Не настраивать |
| procedure.repeat | formatter_procedure.format_procedure | one independent repeated layout, full rollback on difference/diagnostic | safety | None; Не отключать |
| ordinary.repeat | formatter.format_sql | tested externally; no extra runtime second format | runtime | None; Не добавлять/убирать проверки при миграции |
| CP.rules | formatter_case.RULES | ['CP01', 'CP02', 'CP03', 'CP04', 'CP05'] | safety | None; Whitelist unchanged; no full sqlfluff fix |
| CP.target_proof | formatter_case.normalize_case | CP02 lower, other CP upper; same length leaf replacement/ancestry | safety | None; Changing policies requires witness update; not config-only today |
| dialect.version | teradata_procedure_grammar.procedure_config | 4.4.0 only | safety | None; Private hook pinned, no upgrade |
| configuration.discovery | formatter_runtime.project_config / formatter_case.normalize_case | absolute project .sqlfluff; ignore cwd/home; inline comments are data | safety | None; Resolver must keep no implicit sources |
| profiles | dbeaver_adapter.PROFILE_FORMATTERS | ['personal', 'corporate'] | profile | profiles; Same format_bytes function; no differing Python logic |
| format_sql.diagnostics | formatter.format_sql | None emits stderr; list collects | runtime | None; Keep API |
| CLI.path | formatter.main | argv[1] or input.sql | transport | None; Keep positional compatibility; future show-config separate argparse branch |
| CLI.stream | formatter.main | UTF-8, newline empty; SQL stdout, diagnostics stderr | transport | None; Keep headless |
| adapter.arguments | dbeaver_adapter.main | exactly one file path; no stdin | transport | None; No change to official entry |
| adapter.encoding | dbeaver_adapter.format_bytes | UTF-8 bytes; decode utf-8-sig | transport | None; Invalid encoding returns original |
| adapter.diagnostics | dbeaver_adapter.format_bytes | C001/E001/E002 validated; E003/E004/unknown -> original | safety | None; Keep strict fallback |
| adapter.streams | dbeaver_adapter.main | stdout only SQL; fd stderr suppressed | safety | None; Keep even native write protection |
| adapter.exit | dbeaver_adapter.main | 0 delivered/fallback; 1 read/write/start; 2 arguments | transport | None; Never use exit alone as editor safety |
| adapter.log.rotation | dbeaver_adapter.log_event | 262144 | runtime | diagnostics.adapter_log_limit; One previous file; safe default |
| trace.enabled | formatter_trace.event | SQL_FORMATTER_TRACE == 1 | diagnostic | diagnostics.trace; Explicit opt-in; environment retained |
| trace.directory | formatter_trace.event / dbeaver_adapter.log_event | SQL_FORMATTER_LOG_DIR else LOCALAPPDATA else tempfile / SQLFormatter/logs | diagnostic | diagnostics.log_directory; Keep writable Windows fallback |
| trace.fields | formatter_trace.STAGES/CODES/SEGMENTS | allowlisted metadata, ms rounded 3; no SQL; no rotation | safety | None; No sensitive strings |
| diagnose.args | diagnose_formatter.main | path personal / corporate log_directory; enables trace | diagnostic | None; Keep separate from editor transport |
| GUI.keys | profile_selector.select_profile | 1/2 incl keypad; Esc/close cancel; mouse fallback | transport | None; No profile autochoice |
| GUI.geometry | profile_selector.select_profile | 300x180 centered; padding20, buttons pady4, label12 | runtime | None; Not SQL settings |
| GUI.topmost_ms | profile_selector.select_profile | 300 | runtime | None; Temporary; focus_force best effort |
| GUI.callback_error | profile_selector.select_profile | raise -> original SQL | safety | None; No silent success |
| DBeaver.timeout | docs/DBEAVER_WINDOWS_SETUP.md | 120000 | external | external.dbeaver_timeout_ms; Manual recommendation, no Python timeout |

## Что является стилем, а что — защитой

1. Стиль: размер отступа, положение запятых, пробельные границы, регистр. Сейчас параметры распределены между Python и `.sqlfluff`; изменение файла не обеспечивает согласованное изменение всех проходов.
2. Профили: Personal/Corporate указывают на одну функцию `format_bytes`. Отличий Python-логики или скрытых индивидуальных настроек нет.
3. Внутренний runtime: include_simple/joins/comment_lists/having/cte/sets/windows/qualify — границы владения AST. Их нельзя подавать как пользовательские возможности отключения отдельных safety-проходов. `_checking` управляет рекурсией проверки процедуры, а не пользовательской отменой идемпотентности.
4. Диагностика и транспорт: переменные среды, каталоги журнала, UTF-8/BOM, правила потока и коды возврата, временный topmost и геометрия GUI. SQL не должен попадать в show-config или журнал.
5. Safety: точные protected spans, AST ownership, атомарность, rollback, narrow token exceptions, CP whitelist, отказ неподдержанного AST. Пользовательских переключателей для них не предлагается.

## Реальная конфигурация SQLFluff

Проектный файл: dialect=teradata, templater=raw, max_line_length=120; exclude_rules=AL01,ST05; space/4; keyword upper, functions upper, identifiers lower (all unquoted), literals upper, types upper. В parser dialect/raw принудительно заданы overrides. CP создаёт отдельный config: rules ровно CP01–CP05, exclude_rules пусто, disable_noqa=True. Inline config comments не обрабатываются обоими runtime-путями. Домашний/cwd config не обнаруживается.

`layout.commas.line_position=leading` и `spacing_after=single` не управляют Python списками: LintFix layout-правил не запускаются. Аналогично max_line_length=120 не является ограничителем длины выдаваемого SQL. Это важное отличие effective SQLFluff values от активного контракта renderer.

CP имеет второй, проверочный слой политики: CP02 допускает ровно lower(), остальные CP — upper(), одинаковая длина и соответствие leaf/AST. Простая смена `.sqlfluff` на другой case policy может привести к безопасному отказу, а не новому стилю. Миграция должна синхронно передавать доказуемую политику генератору и verifier, не расширяя произвольную замену токенов.

## Область капитализации

CP01 — распознанные keywords; CP03 — function_name, включая TO_CHAR. CP02 — unquoted identifiers (базы, таблицы, алиасы, процедура, переменные/параметры в распознанном AST). SQLFluff не гарантирует бизнес-различение built-in и пользовательской функции: UDF, разобранная как function_name, тоже следует CP03. Нельзя обещать отдельный builtin_function_case без дополнительного исследования AST/каталога функций. Quoted identifiers, строковые литералы, комментарии остаются точными; CP04 меняет только распознанные boolean/null literals. CP05 — типы данных. Unicode-преобразование с изменением длины консервативно отвергается.

## Несогласованные будущие значения

100 символов, adaptive functions, CALL trailing, IN/VALUES pack_to_width и сохранение «допустимых» ручных переносов относятся к B10.6. Точный критерий допустимости и пороги пока не определены. `column_alias_as=require` противоречит текущему preserve: вставка AS не разрешена валидатором. Эти значения не добавлены в production и не подменяют существующие настройки.

### Проверенный пример CP (синтетический)

Вход: `select to_char(T.Created, 'YYYY'), My_Func(T.ID) AS Alias from My_DB.My_Table AS T;`

Результат содержит `TO_CHAR(t.created, 'YYYY')`, `MY_FUNC(t.id) AS alias`, `FROM my_db.my_table t`. Литерал сохранён, table AS удалён по B10.4. CALL-имя процедуры, разобранное как identifier, следует CP02 — это отличается от function_name внутри выражения и не должно скрываться именем `builtin_function_case`.

Внутренние лимиты B10.5 ограничивают число записей и объём исходных ключей, а не гарантируют фиксированный размер памяти Python-объектов. Они не управляют SQL-output: при превышении лимита вычисление идёт прежним путём.

### Жизненный цикл конфигурации SQLFluff

Установленный SQLFluff 4.4.0 кэширует `load_config_file_as_dict` и `load_config_at_path` по пути на время процесса. Поэтому новый FluffConfig не гарантирует hot reload изменённого .sqlfluff. Это поведение baseline, не новый cache B10.5. Проверка точных bytes в нашем ключе исключает возврат старого proof из нашего cache, но не обещает сброс внутреннего cache SQLFluff. Для действующего файлового runtime после изменения конфигурации нужен новый процесс. Будущий resolver с собственным snapshot и mapping должен явно определить reload policy.

Поле Public? означает поддержанный пользовательский интерфейс/операционный параметр, а не физическую возможность редактировать исходный Python или произвольные ключи .sqlfluff.
