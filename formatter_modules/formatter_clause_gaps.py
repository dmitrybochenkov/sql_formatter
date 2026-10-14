"""Conservative AST-anchored gap formatting for GROUP BY, ORDER BY, FROM.

Only direct commas are list separators. Expressions are never rewritten; any
comment, multiline expression, or ambiguous clause structure is skipped.
"""
import re
from formatter_modules.formatter_edits import Edit
from formatter_modules.formatter_protection import protected_spans

PATTERNS = {
    'groupby_clause': re.compile(r'GROUP\s+BY\b', re.I),
    'orderby_clause': re.compile(r'ORDER\s+BY\b', re.I),
    'from_clause': re.compile(r'FROM\b', re.I),
}


def clause_gap_edits(source, clause):
    kind = next((k for k in PATTERNS if clause.is_type(k)), None)
    if kind is None or clause.pos_marker is None:
        return None
    start, end = clause.pos_marker.source_slice.start, clause.pos_marker.source_slice.stop
    raw = source[start:end]
    match = PATTERNS[kind].match(raw)
    if not match:
        return None
    # FROM with JOIN or a subquery is not a comma-table list.
    if kind == 'from_clause' and any(s.is_type('join_clause', 'select_statement', 'bracketed') for s in _walk(clause) if s is not clause):
        return None
    commas = sorted((s for s in clause.segments if s.is_type('comma') and s.pos_marker),
                    key=lambda s: s.pos_marker.source_slice.start)
    body_start = start + match.end()
    boundaries = [body_start] + [s.pos_marker.source_slice.stop for s in commas]
    stops = [s.pos_marker.source_slice.start for s in commas] + [end]
    items = []
    for a, b in zip(boundaries, stops):
        fragment = source[a:b]
        if not fragment.strip() or '\n' in fragment.strip() or '\r' in fragment.strip():
            return None
        items.append(fragment.strip())
    if not items:
        return None
    # Comments may be outside the clause's direct descendants; check raw span.
    if any(p.kind in ('line_comment', 'block_comment') and p.start < end and p.end > start for p in protected_spans(source)):
        return None
    # Require only whitespace around each item, never rewrite an expression.
    # Existing newlines between elements are fine, but expressions themselves
    # must be one line (enforced conservatively below).
    if any('\n' in item or '\r' in item for item in items):
        return None
    line_start = source.rfind('\n', 0, start) + 1
    base = source[line_start:start]
    if base.strip() or '\t' in base:
        return None
    title = ' '.join(raw[:match.end()].split()).upper()
    if kind == 'from_clause' and len(items) == 1:
        rendered = title + ' ' + items[0]
    elif kind != 'from_clause' and len(items) == 1:
        rendered = title + ' ' + items[0]
    else:
        indent = base + '    '
        rendered = title + '\n' + indent + items[0]
        for item in items[1:]:
            rendered += '\n' + indent + ', ' + item
    if rendered == raw:
        return []
    return [Edit(start, end, rendered, 'CLAUSE-GAPS', kind)]


def _walk(node):
    yield node
    for child in node.segments:
        yield from _walk(child)
