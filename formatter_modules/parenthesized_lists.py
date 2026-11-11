"""Only AST-owned IN and VALUES separators; item bytes stay opaque.

Absent mode is a no-op for release compatibility. Each list is one B2 group.
"""
from contextlib import contextmanager
from contextvars import ContextVar

from formatter_modules.formatter_config import current_settings
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_edits import Edit, Diagnostic, apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans


def walk(node):
    yield node
    for child in node.segments:
        yield from walk(child)


def bounds(node):
    span = node.pos_marker.source_slice
    return span.start, span.stop


def targets(tree):
    for parent in walk(tree):
        code = [s for s in parent.segments if s.is_code and not s.is_meta]
        for i, node in enumerate(code):
            if not node.is_type('bracketed'):
                continue
            if not (parent.is_type('values_clause') or
                    (parent.is_type('expression') and i and code[i-1].is_type('keyword')
                     and code[i-1].raw.upper() == 'IN')):
                continue
            # Never treat a query's SELECT/commas as scalar list items.
            if any(n.is_type('select_statement', 'set_expression', 'with_compound_statement') for n in walk(node)):
                continue
            yield node


_EXTERNAL_INDENT = ContextVar('parenthesized_external_indent', default=0)


@contextmanager
def procedural_list_indent(level):
    token = _EXTERNAL_INDENT.set(level)
    try:
        yield
    finally:
        _EXTERNAL_INDENT.reset(token)


def format_parenthesized_lists(source):
    if current_settings().get('parenthesized_lists', 'mode') is None:
        return source, []
    # Earlier lists can move a later prefix and closing-line suffix. Resolve
    # these local whitespace dependencies before exposing a result to callers.
    count = len(list(targets(source_linter().parse_string(source).tree)))
    diagnostics = []
    seen = set()
    for _ in range(count + 3):
        if source in seen:
            raise ValueError('Parenthesized layout did not converge')
        seen.add(source)
        candidate, warnings = _format_once(source)
        for warning in warnings:
            if warning not in diagnostics:
                diagnostics.append(warning)
        if candidate == source:
            return candidate, diagnostics
        source = candidate
    raise ValueError('Parenthesized layout did not converge')


def _format_once(source):
    settings = current_settings()
    mode = settings.get('parenthesized_lists', 'mode')
    if mode is None:
        return source, []
    limit = settings.get('parenthesized_lists', 'max_line_length')
    parsed = source_linter().parse_string(source)
    if parsed.tree is None or parsed.violations:
        raise ValueError('Parenthesized list requires unambiguous AST')
    protected = protected_spans(source)
    ambiguous = ambiguous_comment_spans(source)
    edits, diagnostics = [], []
    for node in targets(parsed.tree):
        code = [s for s in node.segments if s.is_code and not s.is_meta]
        if len(code) < 3 or not code[0].is_type('start_bracket') or not code[-1].is_type('end_bracket'):
            continue
        opening, closing = bounds(code[0]), bounds(code[-1])
        items, commas, part = [], [], []
        for child in code[1:-1]:
            if child.is_type('comma'):
                if not part:
                    break
                items.append((bounds(part[0])[0], bounds(part[-1])[1], part))
                part = []
                commas.append(bounds(child))
            else:
                part.append(child)
        if not part:
            continue
        items.append((bounds(part[0])[0], bounds(part[-1])[1], part))
        if len(commas) != len(items)-1:
            continue
        start, end = bounds(node)
        comments = [p for p in protected if start <= p.start < end and p.kind.endswith('comment')]
        if any(start <= p.start < end for p in ambiguous):
            diagnostics.append(Diagnostic('SQLFMT-C001', node.pos_marker.line_no,
                                          'Неоднозначные комментарии скобочного списка: список сохранён'))
            continue
        prefix = apply_edits(source[:start], [e for e in edits if e.end <= start])
        line = prefix[prefix.rfind('\n')+1:]
        base = line[:len(line)-len(line.lstrip(' \t'))]
        indent = base + '    '
        raw = [source[a:b] for a,b,_ in items]
        simple = all(len(ns) == 1 and ns[0].is_type('numeric_literal', 'quoted_literal', 'literal',
                         'null_literal', 'boolean_literal', 'named_parameter', 'column_reference')
                     for _,_,ns in items)
        multiline = mode == 'multiline' or bool(comments) or any('\n' in t or '\r' in t for t in raw)
        if mode == 'adaptive':
            line_end = source.find('\n', closing[1])
            suffix = source[closing[1]:line_end if line_end >= 0 else len(source)]
            multiline = multiline or not simple or _EXTERNAL_INDENT.get()+len(line)+2+len(', '.join(raw))+len(suffix) > limit
        group = f'parenthesized:{start}:{end}'
        local = []

        def add(a,b,value):
            if source[a:b] != value:
                local.append(Edit(a,b,value,'PAREN-LIST',group,group))

        def gap(a,b,value,comma=None):
            spans = [p for p in comments if a <= p.start and p.end <= b]
            if comma and any(p.start < comma[1] and p.end > comma[0] for p in spans):
                return False
            points = ([(a,spans[0].start)] + [(x.end,y.start) for x,y in zip(spans,spans[1:])]
                      + [(spans[-1].end,b)]) if spans else [(a,b)]
            for x,y in points:
                text = source[x:y]
                if comma and x <= comma[0] < comma[1] <= y:
                    text = source[x:comma[0]] + source[comma[1]:y]
                if text.strip():
                    return False
            if not spans:
                add(a,b,value)
                return True
            trailing = '\n' not in source[a:spans[0].start] and '\r' not in source[a:spans[0].start]
            if trailing and len(spans)>1:
                return False
            for i,(x,y) in enumerate(points):
                replacement = ' ' if i == 0 and trailing else '\n'+indent
                if i == len(points)-1:
                    replacement = value
                add(x,y,replacement)
            return True

        okay = gap(opening[1],items[0][0], '\n'+indent if multiline else '')
        width = _EXTERNAL_INDENT.get()+len(indent)+len(raw[0])
        for left, right, comma, text in zip(items,items[1:],commas,raw[1:]):
            pack = multiline and mode == 'adaptive' and simple and not comments and width+2+len(text) <= limit
            if not multiline or pack:
                value = ', '
                width += 2+len(text)
            else:
                value = '\n'+indent+', '
                width = _EXTERNAL_INDENT.get()+len(indent)+2+len(text)
            okay = gap(left[1],right[0],value,comma) and okay
        okay = gap(items[-1][1],closing[0], '\n'+base if multiline else '') and okay
        if okay:
            edits.extend(local)
        else:
            diagnostics.append(Diagnostic('SQLFMT-C001', node.pos_marker.line_no,
                                          'Принадлежность комментариев списка неоднозначна: вся группа сохранена'))
    planned, warnings = plan_edits(source, edits, protected=[(p.start,p.end) for p in protected])
    return apply_edits(source, planned), diagnostics+warnings
