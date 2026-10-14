"""AST-anchored whitespace edits for SELECT lists containing quoted values.

Never replaces an expression: only whitespace preceding the first element and
between AST-delimited comma-separated elements is edited.
"""
import re
from formatter_modules.formatter_edits import Edit
from formatter_modules.formatter_protection import protected_spans


def select_gap_edits(source, clause):
    if not clause.is_type('select_clause') or clause.pos_marker is None:
        return None
    start, end = clause.pos_marker.source_slice.start, clause.pos_marker.source_slice.stop
    elements = sorted((s for s in clause.segments if s.is_type('select_clause_element') and s.pos_marker),
                      key=lambda s: s.pos_marker.source_slice.start)
    commas = sorted((s for s in clause.segments if s.is_type('comma') and s.pos_marker),
                    key=lambda s: s.pos_marker.source_slice.start)
    if not elements or len(commas) != len(elements) - 1:
        return None
    positions = [(e.pos_marker.source_slice.start, e.pos_marker.source_slice.stop) for e in elements]
    if any(a >= b or a < start or b > end for a, b in positions):
        return None
    if any(not (positions[i][1] <= c.pos_marker.source_slice.start <
                c.pos_marker.source_slice.stop <= positions[i+1][0])
           for i, c in enumerate(commas)):
        return None
    line_start = source.rfind('\n', 0, start) + 1
    base = source[line_start:start]
    if base.strip():
        return None
    indent = base + '    '
    prefix = source[start:positions[0][0]]
    if not re.match(r'^SELECT\b', prefix, re.I):
        return None
    # Retain the exact modifier spelling and order, normalize header whitespace.
    header = ' '.join(prefix.split())
    if not header:
        return None
    gaps = [(start, positions[0][0], header + '\n' + indent)]
    for i, comma in enumerate(commas):
        gaps.append((positions[i][1], positions[i+1][0], '\n' + indent + ', '))
    protected = protected_spans(source)
    result = []
    for a, b, replacement in gaps:
        # A gap may only contain whitespace and (for later gaps) its comma.
        raw = source[a:b]
        if (a == start and not re.fullmatch(r'(?is)\s*SELECT\b(?:\s+[\w]+)*\s*', raw)):
            return None
        if a != start and not re.fullmatch(r'\s*,\s*', raw):
            return None
        if any(a < p.end and b > p.start for p in protected):
            return None
        if raw != replacement:
            result.append(Edit(a, b, replacement, 'LIST-GAPS', 'select_clause'))
    return result
