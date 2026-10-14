import re
import sys

from pathlib import Path
from dataclasses import replace

from sqlfluff.core import Linter

from formatter_modules.formatter_edits import Edit, apply_edits, emit_diagnostics, plan_edits, Diagnostic
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans
from formatter_modules.formatter_guarded_pass import guarded_pass
from formatter_modules.formatter_lists import normalize_simple_list
from formatter_modules.formatter_list_gaps import select_gap_edits
from formatter_modules.formatter_clause_gaps import clause_gap_edits, nested_query_gap_edits, commented_clause_gap_edits
from formatter_modules.formatter_comment_lists_v3 import commented_select_edits

DIALECT = "teradata"
INDENT = " " * 4


def walk(segment):
    """Обход синтаксического дерева SQLFluff."""
    yield segment
    for child in segment.segments:
        yield from walk(child)


def format_list_clause(source, clause):
    """Форматирует SELECT, GROUP BY и ORDER BY с ведущими запятыми."""
    if clause.pos_marker is None:
        return None

    start = clause.pos_marker.source_slice.start
    end = clause.pos_marker.source_slice.stop
    original = source[start:end]

    # Пока не переставляем комментарии внутри списков.
    # Их обработаем отдельным правилом.
    if any(segment.is_type("comment") for segment in walk(clause)):
        return None

    # Ищем запятые только на верхнем уровне предложения.
    # Запятые внутри функций и вложенных выражений не трогаем.
    commas = [
        segment
        for segment in clause.segments
        if segment.is_type("comma") and segment.pos_marker is not None
    ]

    if clause.is_type("select_clause"):
        match = re.match(r"(?is)^\s*SELECT\b", original)
        keyword = "SELECT"
    elif clause.is_type("groupby_clause"):
        match = re.match(r"(?is)^\s*GROUP\s+BY\b", original)
        keyword = "GROUP BY"
    elif clause.is_type("orderby_clause"):
        match = re.match(r"(?is)^\s*ORDER\s+BY\b", original)
        keyword = "ORDER BY"
    else:
        return None

    if match is None:
        return None

    body_start = start + match.end()

    # Отступ относительно строки, на которой стоит SELECT/GROUP BY.
    line_start = source.rfind("\n", 0, start) + 1
    base_indent = re.match(r"[ \t]*", source[line_start:start]).group()

    item_indent = base_indent + INDENT

    # GROUP BY с одним выражением оставляем горизонтальным.
    if keyword in ("GROUP BY", "ORDER BY") and not commas:
        expression = source[body_start:end].strip()
        return start, end, f"{keyword} {expression}"

    # Разделяем список по запятым верхнего уровня.
    items = []
    cursor = body_start

    for comma in commas:
        comma_start = comma.pos_marker.source_slice.start
        comma_end = comma.pos_marker.source_slice.stop

        items.append(source[cursor:comma_start].strip())
        cursor = comma_end

    items.append(source[cursor:end].strip())

    if not items or any(not item for item in items):
        return None

    formatted = keyword + "\n"
    formatted += item_indent + items[0]

    for item in items[1:]:
        formatted += "\n" + item_indent + ", " + item

    return start, end, formatted


def format_commented_select(source, clause):
    """Переносит запятые SELECT, сохраняя комментарии."""
    if clause.pos_marker is None:
        return []

    segments = [seg for seg in clause.segments if seg.pos_marker is not None]

    elements = [seg for seg in segments if seg.is_type("select_clause_element")]

    commas = [seg for seg in segments if seg.is_type("comma")]

    if len(elements) < 2 or len(commas) != len(elements) - 1:
        return []

    edits = []

    for index, comma in enumerate(commas):
        comma_start = comma.pos_marker.source_slice.start
        comma_end = comma.pos_marker.source_slice.stop
        next_start = elements[index + 1].pos_marker.source_slice.start

        # Проверяем, стоит ли запятая уже перед следующим полем.
        line_start = source.rfind("\n", 0, comma_start) + 1
        before_comma = source[line_start:comma_start]

        if not before_comma.strip():
            # Запятая уже ведущая.
            # Нормализуем пробелы между ней и полем.
            if source[comma_end:next_start] != " ":
                edits.append((comma_end, next_start, " "))
            continue

        # Запятая находится после предыдущего поля.
        # Удаляем её со старого места.
        edits.append((comma_start, comma_end, ""))

        # Добавляем ведущую запятую перед следующим полем.
        edits.append((next_start, next_start, ", "))

    return edits


def format_commented_group_order(source, clause):
    """Форматирует простые списки с комментариями, сохраняя исходные выражения.

    Неподдерживаемые сочетания комментариев и выражений не изменяются.
    """
    if clause.pos_marker is None:
        return None

    start = clause.pos_marker.source_slice.start
    end = clause.pos_marker.source_slice.stop
    original = source[start:end]

    if clause.is_type("groupby_clause"):
        match = re.match(r"(?is)^GROUP\s+BY\b", original)
        keyword = "GROUP BY"
    elif clause.is_type("orderby_clause"):
        match = re.match(r"(?is)^ORDER\s+BY\b", original)
        keyword = "ORDER BY"
    else:
        return None

    if match is None or any(seg.is_type("block_comment") for seg in walk(clause)):
        return None

    # Если список уже начинается с новой строки после ключевого слова,
    # не перестраиваем его повторно.
    # Это предотвращает накопление отступов при повторном форматировании.
    if "\n" in original[match.end() :].split(",", 1)[0]:
        return None

    commas = [
        seg
        for seg in clause.segments
        if seg.is_type("comma") and seg.pos_marker is not None
    ]
    if not commas:
        return None

    line_start = source.rfind("\n", 0, start) + 1
    line_prefix = source[line_start:start]
    # Если GROUP BY / ORDER BY находится посреди строки, пробелы перед
    # предыдущим выражением не являются отступом этой секции.
    base_indent = line_prefix if not line_prefix.strip() else ""
    item_indent = base_indent + INDENT
    body_start = start + match.end()

    # Каждый фрагмент между запятыми содержит ровно одно выражение.
    # Используем границы AST, а не splitlines()/join(): текст выражения
    # (включая литералы, пробелы и скобки) остаётся неизменным.
    boundaries = [body_start]
    boundaries.extend(seg.pos_marker.source_slice.stop for seg in commas)
    stops = [seg.pos_marker.source_slice.start for seg in commas] + [end]
    parts = []

    for index, (part_start, part_end) in enumerate(zip(boundaries, stops)):
        members = [
            seg
            for seg in clause.segments
            if seg.pos_marker is not None
            and seg.pos_marker.source_slice.start >= part_start
            and seg.pos_marker.source_slice.stop <= part_end
            and not seg.is_type(
                "whitespace", "newline", "inline_comment", "block_comment", "comma"
            )
            and not seg.is_meta
        ]
        # В Teradata возможны составные выражения из нескольких сегментов.
        # Объединяем их по исходному диапазону, не редактируя содержимое.
        if not members:
            return None
        expr_start = members[0].pos_marker.source_slice.start
        expr_end = members[-1].pos_marker.source_slice.stop
        if expr_start >= expr_end:
            return None

        comments = [
            seg
            for seg in clause.segments
            if seg.is_type("inline_comment")
            and seg.pos_marker is not None
            and part_start <= seg.pos_marker.source_slice.start < part_end
        ]
        before_comments = []
        after_comments = []
        for comment in comments:
            cs = comment.pos_marker.source_slice.start
            _ = comment.pos_marker.source_slice.stop
            if cs < expr_start:
                # Комментарий до выражения должен начинаться с отдельной строки.
                prefix = source[source.rfind("\n", 0, cs) + 1 : cs]
                if prefix.strip():
                    return None
                before_comments.append(comment.raw)
            elif cs >= expr_end:
                # Справа от выражения комментарий остаётся справа.
                if "\n" in source[expr_end:cs]:
                    return None
                after_comments.append(comment.raw)
            else:
                # Комментарий внутри выражения: не рискуем перестраивать.
                return None

        if len(after_comments) > 1:
            return None

        # Не допускаем постороннего SQL в промежутках между выражением
        # и комментариями (например, сложных конструкций вне AST).
        expr = source[expr_start:expr_end]
        # SQLFluff может включать отступ перед элементом списка в его
        # source_slice. Не переносим этот отступ в новую строку повторно.
        # Удаляем только горизонтальный отступ в начале диапазона,
        # не трогая пробелы внутри выражения или строковых литералов.
        expr = expr.lstrip(" \t\r\n")
        prefix_text = source[part_start:expr_start]
        suffix_text = source[expr_end:part_end]
        for comment in comments:
            raw = source[
                comment.pos_marker.source_slice.start : comment.pos_marker.source_slice.stop
            ]
            prefix_text = prefix_text.replace(raw, "", 1)
            suffix_text = suffix_text.replace(raw, "", 1)
        if prefix_text.strip() or suffix_text.strip():
            return None

        parts.append((expr, before_comments, after_comments))

    lines = [keyword]
    for index, (expr, before_comments, after_comments) in enumerate(parts):
        for comment in before_comments:
            lines.append(item_indent + comment)
        prefix = ", " if index else ""
        line = item_indent + prefix + expr
        if after_comments:
            line += " " + after_comments[0]
        lines.append(line)

    return start, end, "\n".join(lines)


def clean_blank_line_whitespace(source):
    """Очищает пустые строки, не затрагивая литералы и комментарии SQL."""
    parsed = Linter(dialect=DIALECT).parse_string(source)
    if parsed.tree is None:
        raise ValueError("Не удалось разобрать SQL перед очисткой пустых строк.")
    if any(seg.is_type("unparsable") for seg in walk(parsed.tree)):
        raise ValueError("Нераспознанный SQL перед очисткой пустых строк.")

    # Только сегменты whitespace можно безопасно удалить. Пробелы внутри
    # quoted_literal и комментариев не являются whitespace-сегментами.
    spans = [
        (seg.pos_marker.source_slice.start, seg.pos_marker.source_slice.stop)
        for seg in walk(parsed.tree)
        if seg.is_type("whitespace") and seg.pos_marker is not None and not seg.segments
    ]
    edits = []
    for match in re.finditer(r"(?m)^[ \t]+(?=\r?$)", source):
        start, end = match.span()
        if any(a <= start and end <= b for a, b in spans):
            edits.append((start, end))

    for start, end in reversed(edits):
        source = source[:start] + source[end:]
    return source


def format_join_clause(source, clause):
    """Форматирует JOIN, ON и простые цепочки AND."""
    if clause.pos_marker is None:
        return None

    start = clause.pos_marker.source_slice.start
    end = clause.pos_marker.source_slice.stop

    # Пока не перестраиваем JOIN с комментариями.
    if any(segment.is_type("comment") for segment in walk(clause)):
        return None

    on_condition = next(
        (
            segment
            for segment in clause.segments
            if segment.is_type("join_on_condition")
        ),
        None,
    )

    if on_condition is None or on_condition.pos_marker is None:
        return None

    on_start = on_condition.pos_marker.source_slice.start
    on_end = on_condition.pos_marker.source_slice.stop

    # JOIN и таблица остаются на одной строке.
    join_header = source[start:on_start].strip()

    # JOIN с подзапросом пока не перестраиваем целиком,
    # чтобы не пересекались диапазоны изменений.
    if any(seg.is_type("select_statement") for seg in walk(clause)):
        return None

    expression = next(
        (segment for segment in on_condition.segments if segment.is_type("expression")),
        None,
    )

    if expression is None:
        return None

    # Сложные условия с OR пока не меняем.
    if any(
        segment.is_type("binary_operator") and segment.raw_upper == "OR"
        for segment in walk(expression)
    ):
        return None

    # Разделяем только AND верхнего уровня выражения.
    and_segments = [
        segment
        for segment in expression.segments
        if segment.is_type("binary_operator")
        and segment.raw_upper == "AND"
        and segment.pos_marker is not None
    ]

    line_start = source.rfind("\n", 0, start) + 1
    base_indent = re.match(r"[ \t]*", source[line_start:start]).group()

    if not and_segments:
        condition = source[on_start:on_end].strip()
        formatted = join_header + "\n" + base_indent + condition
    else:
        expression_start = expression.pos_marker.source_slice.start
        expression_end = expression.pos_marker.source_slice.stop

        conditions = []
        cursor = expression_start

        for operator in and_segments:
            operator_start = operator.pos_marker.source_slice.start
            operator_end = operator.pos_marker.source_slice.stop

            conditions.append(source[cursor:operator_start].strip())
            cursor = operator_end

        conditions.append(source[cursor:expression_end].strip())

        formatted = join_header + "\n" + base_indent + "ON " + conditions[0]

        for condition in conditions[1:]:
            formatted += "\n" + base_indent + INDENT + "AND " + condition

        # Если перед JOIN стоит комментарий, не вставляем
    # пустую строку между комментарием и JOIN.
    before_join = source[:start]
    previous_line = before_join.rstrip().split("\n")[-1].strip()

    has_comment_before = previous_line.startswith("--") or previous_line.endswith("*/")

    if has_comment_before or before_join.endswith("\n\n"):
        formatted = base_indent + formatted
    else:
        formatted = "\n" + base_indent + formatted

    return start, end, formatted


def format_join_comment_spacing(source, join_clause):
    """Добавляет пустую строку перед комментарием непосредственно перед JOIN."""
    if join_clause.pos_marker is None:
        return None

    join_start = join_clause.pos_marker.source_slice.start

    # Берём только строку непосредственно перед JOIN.
    join_line_start = source.rfind("\n", 0, join_start) + 1
    previous_line_end = join_line_start - 1

    if previous_line_end < 0:
        return None

    previous_line_start = source.rfind("\n", 0, previous_line_end) + 1

    previous_line = source[previous_line_start:previous_line_end].strip()

    # Пока поддерживаем однострочный блочный комментарий.
    if not (previous_line.startswith("/*") and previous_line.endswith("*/")):
        return None

    # Находим переносы строк перед комментарием.
    whitespace_start = previous_line_start

    while whitespace_start > 0 and source[whitespace_start - 1] in "\r\n":
        whitespace_start -= 1

    if whitespace_start == 0:
        return None

    existing = source[whitespace_start:previous_line_start]
    expected = "\n\n"

    if existing == expected:
        return None

    return whitespace_start, previous_line_start, expected


def format_nested_join(source, clause):
    """Форматирует границы JOIN с подзапросом, не трогая его содержимое."""
    if clause.pos_marker is None:
        return []

    if any(seg.is_type("comment") for seg in walk(clause)):
        return []

    start = clause.pos_marker.source_slice.start

    on_condition = next(
        (seg for seg in clause.segments if seg.is_type("join_on_condition")),
        None,
    )

    if on_condition is None or on_condition.pos_marker is None:
        return []

    on_start = on_condition.pos_marker.source_slice.start

    line_start = source.rfind("\n", 0, start) + 1
    base_indent = re.match(r"[ \t]*", source[line_start:start]).group()

    edits = []

    # 1. Пустая строка перед JOIN.
    before = source[:start]
    if not before.endswith("\n\n"):
        edits.append((start, start, "\n"))

    # Находим начало пробельного участка перед ON.
    whitespace_start = on_start

    while whitespace_start > start and source[whitespace_start - 1] in " \t\r\n":
        whitespace_start -= 1

    whitespace = source[whitespace_start:on_start]

    # Нормализуем пробелы перед ON:
    # ровно один перенос строки и нужный отступ.
    expected = "\n" + base_indent

    if whitespace != expected:
        edits.append((whitespace_start, on_start, expected))

    return edits


def format_where_clause(source, clause):
    """Форматирует простые цепочки AND в WHERE."""
    if clause.pos_marker is None:
        return None

    start = clause.pos_marker.source_slice.start
    end = clause.pos_marker.source_slice.stop

    # Комментарии пока сохраняем без перестановок.
    if any(seg.is_type("comment") for seg in walk(clause)):
        return None

    expression = next(
        (seg for seg in clause.segments if seg.is_type("expression")),
        None,
    )

    if expression is None or expression.pos_marker is None:
        return None

    # Проверяем только OR на верхнем уровне выражения.
    # OR внутри скобок не мешает разделению внешних AND.
    if any(
        seg.is_type("binary_operator") and seg.raw_upper == "OR"
        for seg in expression.segments
    ):
        return None

    and_segments = [
        seg
        for seg in expression.segments
        if seg.is_type("binary_operator")
        and seg.raw_upper == "AND"
        and seg.pos_marker is not None
    ]

    expression_start = expression.pos_marker.source_slice.start
    expression_end = expression.pos_marker.source_slice.stop

    line_start = source.rfind("\n", 0, start) + 1
    base_indent = re.match(r"[ \t]*", source[line_start:start]).group()

    # Одно условие: WHERE condition
    if not and_segments:
        condition = source[expression_start:expression_end].strip()
        return start, end, "WHERE " + condition

    conditions = []
    cursor = expression_start

    for operator in and_segments:
        operator_start = operator.pos_marker.source_slice.start
        operator_end = operator.pos_marker.source_slice.stop

        conditions.append(source[cursor:operator_start].strip())
        cursor = operator_end

    conditions.append(source[cursor:expression_end].strip())

    if any(not condition for condition in conditions):
        return None

    # Не дублируем существующее WHERE 1=1.
    if re.fullmatch(r"1\s*=\s*1", conditions[0]):
        conditions = conditions[1:]

    formatted = "WHERE 1=1"

    for condition in conditions:
        formatted += "\n" + base_indent + INDENT + "AND " + condition

    return start, end, formatted


def format_clause_spacing(source):
    """Одна пустая строка перед SQL-блоками, включая предшествующие комментарии.

    Меняем только целые визуально пустые строки. Содержимое SQL-литералов,
    quoted identifiers и блочных комментариев не редактируем.
    """
    import unicodedata

    # Лексическая защита работает и тогда, когда SQLFluff не может разобрать
    # нестандартный пробел (например NBSP) между SQL-блоками.
    protected = [False] * len(source)
    state = "code"
    i = 0
    while i < len(source):
        ch = source[i]
        nxt = source[i + 1] if i + 1 < len(source) else ""
        if state == "code":
            if ch == "'":
                protected[i] = True
                state = "single"
            elif ch == '"':
                protected[i] = True
                state = "double"
            elif ch == "-" and nxt == "-":
                protected[i] = protected[i + 1] = True
                i += 1
                state = "line_comment"
            elif ch == "/" and nxt == "*":
                protected[i] = protected[i + 1] = True
                i += 1
                state = "block_comment"
        elif state == "single":
            protected[i] = True
            if ch == "'":
                if nxt == "'":
                    protected[i + 1] = True
                    i += 1
                else:
                    state = "code"
        elif state == "double":
            protected[i] = True
            if ch == '"':
                if nxt == '"':
                    protected[i + 1] = True
                    i += 1
                else:
                    state = "code"
        elif state == "line_comment":
            if ch in "\r\n":
                state = "code"
            else:
                protected[i] = True
        elif state == "block_comment":
            protected[i] = True
            if ch == "*" and nxt == "/":
                protected[i + 1] = True
                i += 1
                state = "code"
        i += 1

    lines = source.splitlines(keepends=True)
    starts = []
    offset = 0
    for line in lines:
        starts.append(offset)
        offset += len(line)

    def visual_blank(line):
        content = line.rstrip("\r\n")
        return all(ch.isspace() or unicodedata.category(ch) == "Cf" for ch in content)

    keyword = re.compile(
        r"(?i)^(?:WHERE|GROUP\s+BY|HAVING|ORDER\s+BY|"
        r"(?:(?:LEFT|RIGHT|FULL)(?:\s+OUTER)?|INNER|CROSS|NATURAL)\s+JOIN|JOIN)\b"
    )
    edits = []
    for idx, line in enumerate(lines):
        content = line.rstrip("\r\n")
        stripped = content.lstrip(" \t")
        if not keyword.match(stripped):
            continue
        token_pos = starts[idx] + len(content) - len(stripped)
        if token_pos < len(protected) and protected[token_pos]:
            continue

        # Пустые строки непосредственно перед секцией (если они есть).
        # Не вставляем пустую строку между комментарием и секцией,
        # если их изначально разделял один перенос.
        block = idx
        while block > 0 and visual_blank(lines[block - 1]):
            block -= 1
        if block < idx:
            left = starts[block]
            right = starts[idx]
            if not any(protected[left:right]):
                newline = "\r\n" if "\r\n" in source else "\n"
                expected = newline
                if source[left:right] != expected:
                    edits.append((left, right, expected))

        # Комментарии, непосредственно примыкающие к секции, образуют
        # с ней один блок. При наличии пустых строк между ними выше
        # сохраняется ровно одна пустая строка.
        comment_idx = block
        while comment_idx > 0:
            prev = lines[comment_idx - 1].strip()
            if prev.startswith("--") or (prev.startswith("/*") and prev.endswith("*/")):
                comment_idx -= 1
            else:
                break
        first = comment_idx
        while first > 0 and visual_blank(lines[first - 1]):
            first -= 1
        if first > 0 and first < comment_idx:
            left = starts[first]
            right = starts[comment_idx]
            if not any(protected[left:right]):
                newline = "\r\n" if "\r\n" in source else "\n"
                expected = newline
                if source[left:right] != expected:
                    edits.append((left, right, expected))

    for left, right, replacement in sorted(set(edits), reverse=True):
        source = source[:left] + replacement + source[right:]
    return source


def format_semicolons(source):
    """Переносит настоящие SQL-разделители на отдельную строку."""
    linter = Linter(dialect=DIALECT)
    parsed = linter.parse_string(source)

    if parsed.tree is None:
        raise ValueError("Не удалось разобрать SQL.")

    if any(seg.is_type("unparsable") for seg in walk(parsed.tree)):
        raise ValueError("SQL содержит нераспознанные конструкции.")

    edits = []

    for segment in walk(parsed.tree):
        if not segment.is_type("statement_terminator"):
            continue

        if segment.pos_marker is None:
            continue

        start = segment.pos_marker.source_slice.start

        # Находим только пробелы и переводы строк перед ;
        whitespace_start = start

        while whitespace_start > 0 and source[whitespace_start - 1] in " \t\r\n":
            whitespace_start -= 1

        # Не трогаем ; в начале файла.
        if whitespace_start == 0:
            continue

        existing = source[whitespace_start:start]
        expected = "\n"

        if existing != expected:
            edits.append((whitespace_start, start, expected))

    result = source

    for start, end, replacement in sorted(
        edits, key=lambda item: item[0], reverse=True
    ):
        result = result[:start] + replacement + result[end:]

    return result


def sql_tokens(source):
    """Возвращает SQL-токены и комментарии отдельно."""
    parsed = Linter(dialect=DIALECT).parse_string(source)

    if parsed.tree is None:
        raise ValueError("Не удалось разобрать SQL")

    tokens = []
    comments = []

    def collect(segment):
        if segment.segments:
            for child in segment.segments:
                collect(child)
            return

        if segment.is_type(
            "whitespace",
            "newline",
            "end_of_file",
            "indent",
            "dedent",
            "meta",
        ):
            return

        if segment.is_type("inline_comment", "block_comment"):
            comments.append(segment.raw)
            return

        tokens.append((segment.get_type(), segment.raw))

    collect(parsed.tree)

    return tokens, comments


def remove_formatter_where_prefix(tokens):
    """Нормализует служебный префикс WHERE 1=1 AND."""
    result = []
    i = 0

    expected = [
        ("numeric_literal", "1"),
        ("raw_comparison_operator", "="),
        ("numeric_literal", "1"),
        ("binary_operator", "AND"),
    ]

    while i < len(tokens):
        kind, value = tokens[i]
        result.append(tokens[i])
        i += 1

        if (
            kind == "keyword"
            and value.upper() == "WHERE"
            and tokens[i : i + 4] == expected
        ):
            i += 4

    return result


def _validation_snapshot(source):
    """Keep clause ownership alongside exact tokens; never casefold SQL text."""
    tree = Linter(dialect=DIALECT).parse_string(source).tree
    if tree is None or any(s.is_type('unparsable') for s in walk(tree)):
        raise ValueError('Не удалось разобрать SQL для проверки сохранности')
    tokens, comments, wheres, counts = [], [], {}, {}
    clause_headers = {'select_clause': 'SELECT', 'from_clause': 'FROM', 'where_clause': 'WHERE'}
    scoped = {'statement', 'select_statement', 'select_clause', 'from_clause', 'where_clause'}

    def collect(node, context=(), parent=None):
        kind = node.get_type()
        if kind in scoped:
            ordinal = counts.get(kind, 0)
            counts[kind] = ordinal + 1
            context = context + ((kind, ordinal),)
        if node.is_type('where_clause'):
            expression = next((s for s in node.segments if s.is_type('expression')), None)
            operators = [s.raw_upper for s in expression.segments
                         if s.is_type('binary_operator')] if expression is not None else []
            # Direct expression children exclude BETWEEN's keyword AND and
            # ANDs inside brackets/subqueries. Existing prefixes stay exact.
            wheres[context] = (len(tokens) + 1, 'AND' in operators and 'OR' not in operators)
        if node.segments:
            for child in node.segments:
                collect(child, context, node)
        elif node.is_meta or node.is_type('whitespace', 'newline', 'end_of_file'):
            return
        elif node.is_type('comment'):
            comments.append(node.raw)
        else:
            header = (parent is not None and parent.get_type() in clause_headers
                      and node.is_type('keyword')
                      and node.raw_upper == clause_headers[parent.get_type()])
            tokens.append((kind, node.raw, context, header))

    collect(tree)
    return tokens, comments, wheres


def validate_sql_unchanged(original, formatted):
    """Validate exact tokens, with two narrowly specified AST exceptions."""
    before, before_comments, original_wheres = _validation_snapshot(original)
    after, after_comments, formatted_wheres = _validation_snapshot(formatted)
    prefix = [('numeric_literal', '1'), ('raw_comparison_operator', '='),
              ('numeric_literal', '1'), ('binary_operator', 'AND')]

    def has_prefix(tokens, offset, existing=False):
        values = [(t[0], t[1]) for t in tokens[offset:offset + 4]]
        if existing and len(values) == 4 and values[3][0] == 'binary_operator':
            values[3] = (values[3][0], values[3][1].upper())
        return values == prefix

    removed = set()
    for context, (offset, eligible) in original_wheres.items():
        candidate = formatted_wheres.get(context)
        if candidate is None:
            continue
        after_offset = candidate[0]
        # Only an insertion in this particular WHERE may be discounted.
        # Never remove a prefix that was present in the input or accept its
        # deletion. Exact comparison catches duplicates and all other edits.
        if eligible and not has_prefix(before, offset, existing=True) and has_prefix(after, after_offset):
            removed.update(range(after_offset, after_offset + 4))
    after = [t for i, t in enumerate(after) if i not in removed]

    def same(left, right):
        if left == right:
            return True
        kind, raw, context, header = left
        return (header and right[3] and kind == right[0] == 'keyword'
                and context == right[2] and raw.upper() == right[1])

    if len(before) != len(after) or any(not same(a, b) for a, b in zip(before, after)):
        import difflib
        diff = ''.join(difflib.unified_diff(
            [f'{t[0]}: {t[1]!r} ({t[2]})\n' for t in before],
            [f'{t[0]}: {t[1]!r} ({t[2]})\n' for t in after],
            fromfile='Исходный SQL', tofile='Отформатированный SQL'))
        raise ValueError('Форматирование изменило SQL-токены или их принадлежность!\n' + diff)
    if before_comments != after_comments:
        raise ValueError('Форматирование изменило комментарии!')


def normalize_groupby_header_comments(source):
    """Переносит комментарий с GROUP BY над секцией, только если есть список.

    Консервативный fallback: комментарий не должен мешать разбору элементов.
    Проверяем, что это реальный SQL-комментарий по позициям AST, а не текст
    внутри строкового литерала. Содержимое комментария не изменяется.
    """
    parsed = Linter(dialect=DIALECT).parse_string(source)
    if parsed.tree is None:
        return source

    comment_starts = {
        seg.pos_marker.source_slice.start
        for seg in walk(parsed.tree)
        if seg.is_type("inline_comment") and seg.pos_marker is not None
    }
    edits = []
    pattern = re.compile(r"(?m)^([ \t]*)(GROUP[ \t]+BY)[ \t]+(--[^\r\n]*)(\r?\n)", re.I)
    for match in pattern.finditer(source):
        indent, keyword, comment, newline = match.groups()
        comment_start = match.start(3)
        if comment_start not in comment_starts:
            continue
        # Поддерживаем только простые списки с запятой до следующей секции.
        tail = source[match.end():]
        next_clause = re.search(r"(?im)^\s*(?:HAVING|ORDER\s+BY|QUALIFY|LIMIT|UNION|INTERSECT|EXCEPT)\b|^\s*\)", tail)
        body = tail[:next_clause.start()] if next_clause else tail
        if not re.search(r",", body):
            continue
        replacement = indent + comment + newline + indent + keyword + newline
        edits.append((match.start(), match.end(), replacement))
    for start, end, replacement in reversed(edits):
        source = source[:start] + replacement + source[end:]
    return source


def normalize_select_field_indents(source):
    """Выравнивает уже многострочные поля SELECT по позициям SQLFluff.

    Не перемещает SQL, запятые или комментарии; изменяет только
    горизонтальные отступы в начале строк с элементами списка.
    """
    parsed = Linter(dialect=DIALECT).parse_string(source)
    if parsed.tree is None or any(seg.is_type("unparsable") for seg in walk(parsed.tree)):
        return source

    edits = []
    for clause in walk(parsed.tree):
        if not clause.is_type("select_clause") or clause.pos_marker is None:
            continue
        start = clause.pos_marker.source_slice.start
        clause_line_start = source.rfind("\n", 0, start) + 1
        before_keyword = source[clause_line_start:start]
        if before_keyword.strip():
            # SELECT находится посреди SQL-строки: не угадываем уровень.
            continue
        indent = before_keyword + INDENT
        elements = [seg for seg in clause.segments
                    if seg.is_type("select_clause_element") and seg.pos_marker]
        for element in elements:
            pos = element.pos_marker.source_slice.start
            line_start = source.rfind("\n", 0, pos) + 1
            if line_start == clause_line_start:
                # Поле пока стоит на строке SELECT — это отдельное правило.
                continue
            prefix = source[line_start:pos]
            if re.fullmatch(r"[ \t]*", prefix):
                edits.append((line_start, pos, indent))
            elif re.fullmatch(r"[ \t]*,[ \t]*", prefix):
                # Запятая уже ведущая: сохраняем её и один пробел после.
                edits.append((line_start, pos, indent + ", "))

    # Вложенные SELECT имеют собственные позиции; пересечений здесь нет.
    for start, end, replacement in sorted(edits, reverse=True):
        source = source[:start] + replacement + source[end:]
    return source


def remove_select_blank_lines(source):
    """Удаляет пустые строки только внутри SELECT, не трогая литералы/комментарии."""
    parsed = Linter(dialect=DIALECT).parse_string(source)
    if parsed.tree is None or any(seg.is_type("unparsable") for seg in walk(parsed.tree)):
        return source

    # Позиции защищённых токенов: пустые строки в их тексте являются данными.
    protected = [
        (seg.pos_marker.source_slice.start, seg.pos_marker.source_slice.stop)
        for seg in walk(parsed.tree)
        if seg.pos_marker is not None and not seg.segments
        and (seg.is_type("inline_comment", "block_comment")
             or "literal" in seg.get_type())
    ]
    edits = set()
    for clause in walk(parsed.tree):
        if not clause.is_type("select_clause") or clause.pos_marker is None:
            continue
        begin = clause.pos_marker.source_slice.start
        end = clause.pos_marker.source_slice.stop
        # A scalar subquery has its own clause spacing; its blank lines are
        # not gaps between fields of the containing SELECT list.
        children = [seg.pos_marker.source_slice for seg in walk(clause)
                    if seg.is_type("select_statement") and seg.pos_marker]
        # Удаляем только целиком пустую строку, включая её перевод строки.
        # Не трогаем строки с SQL, комментариями и содержимым литералов.
        first_line_end = source.find("\n", begin, end)
        if first_line_end < 0:
            continue
        for match in re.finditer(r"(?m)^[^\S\r\n]*\r?\n", source[first_line_end + 1:end]):
            a = first_line_end + 1 + match.start()
            b = first_line_end + 1 + match.end()
            if (not any(a < stop and b > start for start, stop in protected)
                    and not any(a < span.stop and b > span.start for span in children)):
                edits.add((a, b))

    for a, b in sorted(edits, reverse=True):
        source = source[:a] + source[b:]
    return source


def format_sql(source, diagnostics=None):
    # SQLFluff normalises CR/CRLF before assigning source offsets. Until a
    # source map exists, do not parse or modify such input (including literals).
    if "\r" in source:
        warning = Diagnostic("SQLFMT-E003", source.count("\n", 0, source.index("\r")) + 1,
                             "CR/CRLF: AST-позиции ненадёжны; исходный SQL сохранён без изменений")
        if diagnostics is not None:
            diagnostics.append(warning)
        else:
            emit_diagnostics([warning])
        return source

    original_source = source
    source = normalize_groupby_header_comments(source)
    linter = Linter(dialect=DIALECT)
    parsed = linter.parse_string(source)

    if parsed.tree is None:
        raise ValueError("SQLFluff не смог разобрать SQL.")

    # При ошибках синтаксического разбора не меняем запрос.
    if any(segment.is_type("unparsable") for segment in walk(parsed.tree)):
        raise ValueError("Обнаружен нераспознанный SQL. Форматирование отменено.")

    # Prepare supported query boundaries. Reparse after changing whitespace so
    # all existing renderers and B2 checks use offsets from the same snapshot.
    nested_edits, nested_statements = nested_query_gap_edits(
        source, parsed.tree, include_simple=True, include_joins=True, include_comment_lists=True)
    boundary_edits, boundary_warnings = plan_edits(
        source, nested_edits,
        protected=[(span.start, span.end) for span in protected_spans(source)],
    )
    rejected_groups = ({e.group_id for e in nested_edits}
                       - {e.group_id for e in boundary_edits})
    nested_statements = {i for i in nested_statements
                         if f'nested-select:{i}' not in rejected_groups}
    if boundary_edits:
        source = apply_edits(source, boundary_edits)
        parsed = linter.parse_string(source)
        if parsed.tree is None or any(s.is_type("unparsable") for s in walk(parsed.tree)):
            raise ValueError("Не удалось разобрать SQL после оформления границ клауз.")

    statements = [s for s in parsed.tree.segments if s.is_type('statement')]
    nested_wheres = {id(s) for i, statement in enumerate(statements)
                     if i in nested_statements for s in walk(statement)
                     if s.is_type('where_clause')}
    nested_froms = {id(s) for i, statement in enumerate(statements)
                   if i in nested_statements for s in walk(statement)
                   if s.is_type('from_clause')}
    basic_lists = {id(s) for i, statement in enumerate(statements)
                   if i in nested_statements for s in walk(statement)
                   if s.is_type('groupby_clause', 'orderby_clause')}
    basic_joins = {id(s) for i, statement in enumerate(statements)
                   if i in nested_statements for s in walk(statement)
                   if s.is_type('join_clause')}
    edits = []
    structural_warnings = list(boundary_warnings)
    for statement in statements:
        for clause in walk(statement):
            if id(clause) in basic_lists and commented_clause_gap_edits(source, clause) is None:
                structural_warnings.append(Diagnostic(
                    'SQLFMT-C001', source.count('\n', 0, clause.pos_marker.source_slice.start) + 1,
                    'Принадлежность комментариев списка неоднозначна; список сохранён без изменений'))
    for segment in walk(parsed.tree):
        if id(segment) not in nested_wheres:
            continue
        expression = next(s for s in segment.segments if s.is_type('expression'))
        operators = {s.raw_upper for s in expression.segments if s.is_type('binary_operator')}
        if {'AND', 'OR'} <= operators:
            structural_warnings.append(Diagnostic(
                'SQLFMT-W001', source.count('\n', 0, segment.pos_marker.source_slice.start) + 1,
                'Смешанные AND/OR верхнего уровня: WHERE не перестраивается'))

    def add_edits(segment, candidates):
        """Keep each node's related edits atomic; reserve nested SELECT text."""
        marker = segment.pos_marker
        owner = f"{segment.get_type()}[{marker.source_slice.start}:{marker.source_slice.stop}]"
        group = []
        for candidate in candidates:
            edit = (candidate if isinstance(candidate, Edit)
                    else Edit(*candidate, "LEGACY-AST", owner))
            if source[edit.start:edit.end] != edit.replacement:
                group.append(replace(edit, group_id=owner))
        children = [child for child in walk(segment)
                    if child is not segment and child.is_type("select_statement")
                    and child.pos_marker is not None]
        for edit in group:
            for child in children:
                span = child.pos_marker.source_slice
                if edit.start < span.stop and edit.end > span.start:
                    structural_warnings.append(Diagnostic(
                        "SQLFMT-E001", source.count("\n", 0, edit.start) + 1,
                        f"Правка {edit.rule_id} ({owner}) [{edit.start}:{edit.end}] "
                        f"затрагивает дочерний SELECT [{span.start}:{span.stop}]; "
                        "вся группа пропущена"))
                    return
        edits.extend(group)

    for segment in walk(parsed.tree):
        if id(segment) in basic_lists:
            continue  # Prepared by the AST gap pass; never includes OVER.
        if segment.is_type(
            "select_clause",
            "groupby_clause",
            "orderby_clause",
            "from_clause",
        ):
            has_comments = any(
                seg.is_type("inline_comment", "block_comment") for seg in walk(segment)
            )

            if segment.is_type("from_clause"):
                if id(segment) in nested_froms:
                    continue
                gap_edits = clause_gap_edits(source, segment)
                if gap_edits is not None:
                    add_edits(segment, gap_edits)
                continue

            if segment.is_type("select_clause") and has_comments:
                comment_edits = commented_select_edits(source, segment)
                if comment_edits is not None:
                    add_edits(segment, comment_edits)
                else:
                    # Legacy fallback remains guarded until comment ownership
                    # is fully supported by the new AST-based formatter.
                    add_edits(segment, format_commented_select(source, segment))

            elif segment.is_type("groupby_clause", "orderby_clause") and has_comments:
                edit = format_commented_group_order(source, segment)
                if edit is not None:
                    add_edits(segment, [edit])
            else:
                # Обычно нормализуем и уже многострочные списки.
                # Исключение: комментарий после последнего элемента может
                # оказаться вне AST groupby_clause / orderby_clause.
                # Тогда повторное форматирование добавляет отступы.
                start = segment.pos_marker.source_slice.start
                end = segment.pos_marker.source_slice.stop
                original = source[start:end]
                line_end = source.find("\n", end)
                if line_end == -1:
                    line_end = len(source)
                trailing_text = source[end:line_end]
                has_trailing_comment = "--" in trailing_text

                if not (
                    segment.is_type("groupby_clause", "orderby_clause")
                    and "\n" in original
                    and has_trailing_comment
                ):
                    # Stage 4: simple SELECT lists use a single AST-owned edit.
                    # Complex cases and other clauses retain legacy handling.
                    if segment.is_type("select_clause"):
                        gap_edits = select_gap_edits(source, segment)
                        if gap_edits is not None:
                            add_edits(segment, gap_edits)
                            edit = None
                        else:
                            list_edit = normalize_simple_list(source, segment)
                            edit = list_edit
                    else:
                        gap_edits = clause_gap_edits(source, segment)
                        if gap_edits is not None:
                            add_edits(segment, gap_edits)
                            edit = None
                        else:
                            edit = format_list_clause(source, segment)
                    if edit is not None:
                        add_edits(segment, [edit])

        elif segment.is_type("join_clause"):
            if id(segment) in basic_joins:
                continue  # Narrow atomic JOIN/ON edits already applied.
            has_nested_select = any(
                seg.is_type("select_statement") for seg in walk(segment)
            )

            if has_nested_select:
                add_edits(segment, format_nested_join(source, segment))
            else:
                edit = format_join_clause(source, segment)
                if edit is not None:
                    add_edits(segment, [edit])

            comment_spacing = format_join_comment_spacing(source, segment)
            if comment_spacing is not None:
                add_edits(segment, [comment_spacing])

        elif segment.is_type("where_clause"):
            if id(segment) in nested_wheres:
                continue  # Already handled by narrow, atomic AST gap edits.
            edit = format_where_clause(source, segment)
            if edit is not None:
                add_edits(segment, [edit])

    # Этап 2: запрещаем AST-правки, затрагивающие комментарии и
    # литералы. Не пытаемся угадать принадлежность комментария.
    guarded = protected_spans(source)
    ambiguous = ambiguous_comment_spans(source)
    comment_warnings = [
        Diagnostic("SQLFMT-C001", source.count("\n", 0, span.start) + 1,
                   "Комментарий отделён пустой строкой от следующего элемента; принадлежность не определена")
        for span in ambiguous
    ]
    # Этап 1: единая точка контроля пересечений. На переходном этапе
    # сохраняем приоритет короткой правки, но каждое отклонение диагностируем.
    planned, warnings = plan_edits(
        source,
        edits,
        protected=[(span.start, span.end) for span in guarded],
    )
    if diagnostics is not None:
        diagnostics.extend(structural_warnings + comment_warnings + warnings)
    else:
        emit_diagnostics(structural_warnings + comment_warnings + warnings)
    result = apply_edits(source, planned)

    # Переходный этап 3: legacy-проходы больше не получают права
    # безусловно переписывать комментарии и строковые литералы.
    for rule_id, transform in (
        ("BLANK-WHITESPACE", clean_blank_line_whitespace),
        ("CLAUSE-SPACING", format_clause_spacing),
        ("SEMICOLONS", format_semicolons),
        ("SELECT-INDENT", normalize_select_field_indents),
        ("SELECT-BLANKLINES", remove_select_blank_lines),
    ):
        result, pass_warnings = guarded_pass(result, transform, rule_id)
        if diagnostics is not None:
            diagnostics.extend(pass_warnings)
        else:
            emit_diagnostics(pass_warnings)

    validate_sql_unchanged(original_source, result)

    return result.rstrip("\n") + "\n"


def main():
    # Настраиваем UTF-8 только для CLI, не меняя stdout при импорте.
    sys.stdout.reconfigure(encoding="utf-8")
    filename = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("input.sql")
    source = filename.read_text(encoding="utf-8-sig")

    diagnostics = []
    result = format_sql(source, diagnostics=diagnostics)
    emit_diagnostics(diagnostics)
    print(result, end="")


if __name__ == "__main__":
    main()
