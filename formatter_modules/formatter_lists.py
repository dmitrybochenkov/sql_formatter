"""Stage 4: conservative, AST-positioned normalization of simple SQL lists.

Does not parse SQL or move comments/literals. Complex/multiline expressions are
left to future dedicated expression renderers. SQLFluff provides clause spans.
"""
import re
from formatter_modules.formatter_edits import Edit


def normalize_simple_list(source, clause):
    """Produce one edit for an uncomplicated SELECT/GROUP BY/ORDER BY list.

    Return None when comments, nested line breaks in an expression, or unknown
    clause structure make the rewrite unsafe. Preserve SELECT modifiers as-is.
    """
    kind = next((name for name in ('select_clause', 'groupby_clause', 'orderby_clause')
                 if clause.is_type(name)), None)
    if kind is None or clause.pos_marker is None:
        return None
    if any(s.is_type('comment', 'inline_comment', 'block_comment')
           for s in _walk(clause)):
        return None
    start, end = clause.pos_marker.source_slice.start, clause.pos_marker.source_slice.stop
    raw = source[start:end]
    pattern = {'select_clause': r'^SELECT\b', 'groupby_clause': r'^GROUP\s+BY\b',
               'orderby_clause': r'^ORDER\s+BY\b'}[kind]
    header = re.match(pattern, raw, re.I)
    if not header:
        return None
    commas = [s for s in clause.segments if s.is_type('comma') and s.pos_marker]
    # Use AST element start to preserve SELECT DISTINCT/TOP/etc without guessing
    # where the modifier ends. If the grammar doesn't expose elements, skip.
    element_types = {'select_clause': 'select_clause_element',
                     'groupby_clause': 'column_reference',
                     'orderby_clause': 'orderby_clause_element'}
    elements = [s for s in clause.segments if s.is_type(element_types[kind]) and s.pos_marker]
    if kind == 'select_clause' and not elements:
        return None
    if commas and len(elements) != len(commas) + 1:
        return None
    if not elements:
        return None
    # Every comma must separate two elements, not a nested expression.
    positions = [(s.pos_marker.source_slice.start, s.pos_marker.source_slice.stop) for s in elements]
    if any(a >= b or a < start or b > end for a, b in positions):
        return None
    if any(not (positions[i][1] <= commas[i].pos_marker.source_slice.start
                 < commas[i].pos_marker.source_slice.stop <= positions[i+1][0])
           for i in range(len(commas))):
        return None
    prefix = source[start:positions[0][0]]
    # No comments in the prefix; retain SELECT modifiers, including their spelling.
    if kind == 'select_clause':
        title = ' '.join(prefix.split())
    else:
        title = ' '.join(prefix.split())
    if not re.match(pattern, title, re.I):
        return None
    expressions = [source[a:b].strip() for a, b in positions]
    if any(not x or '\n' in x or '\r' in x for x in expressions):
        return None
    # Protect comments that might lie between AST elements (not descendants).
    if any('--' in source[positions[i][1]:positions[i+1][0]] or
           '/*' in source[positions[i][1]:positions[i+1][0]]
           for i in range(len(positions)-1)):
        return None
    line_start = source.rfind('\n', 0, start) + 1
    base = source[line_start:start]
    if base.strip():
        return None
    indent = base + '    '
    if kind != 'select_clause' and len(expressions) == 1:
        replacement = title + ' ' + expressions[0]
    else:
        replacement = title + '\n' + indent + expressions[0]
        replacement += ''.join('\n' + indent + ', ' + x for x in expressions[1:])
    return Edit(start, end, replacement, 'LIST-AST', kind) if replacement != raw else None


def _walk(segment):
    yield segment
    for child in segment.segments:
        yield from _walk(child)
