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


def simple_query_gap_edits(source, tree):
    """Prepare whitespace in top-level SELECT/FROM/WHERE-only statements.

    Run before existing clause renderers so they measure indentation from the
    final clause lines. Never edit across comments, expressions or literals.
    """
    edits = []
    for statement in tree.segments:
        if not statement.is_type('statement'):
            continue
        query = next((s for s in statement.segments if s.is_type('select_statement')), None)
        if query is None or query.pos_marker is None:
            continue
        nodes = list(_walk(query))
        if (sum(s.is_type('select_statement') for s in nodes) != 1
                or any(s.is_type('join_clause', 'over_clause', 'window_specification') for s in nodes)):
            continue
        clauses = [s for s in query.segments if s.is_code and not s.is_meta]
        if ([s.get_type() for s in clauses] not in (
                ['select_clause', 'from_clause'],
                ['select_clause', 'from_clause', 'where_clause'])):
            continue
        select, from_clause = clauses[:2]
        # Comma-table lists have conflicting legacy/golden expectations and
        # remain outside this narrowly scoped pass.
        if sum(s.is_type('from_expression_element') for s in _walk(from_clause)) != 1:
            continue
        start = query.pos_marker.source_slice.start
        owner = f'simple-select[{start}:{query.pos_marker.source_slice.stop}]'

        def gap(a, b, replacement):
            raw = source[a:b]
            if (not raw or raw.isspace()) and raw != replacement:
                edits.append(Edit(a, b, replacement, 'SIMPLE-GAPS', owner, owner))

        # Root query indentation is canonical, not inherited from random input.
        line_start = source.rfind('\n', 0, start) + 1
        gap(line_start, start, '')
        for left, right in zip(clauses, clauses[1:]):
            gap(left.pos_marker.source_slice.stop, right.pos_marker.source_slice.start,
                '\n' if right.is_type('from_clause') else '\n\n')

        # A single FROM target stays beside FROM, including quoted identifiers.
        keyword = next(s for s in from_clause.segments if s.is_type('keyword'))
        target = next(s for s in _walk(from_clause) if s.is_type('from_expression_element'))
        gap(keyword.pos_marker.source_slice.stop, target.pos_marker.source_slice.start, ' ')

        if len(clauses) < 3:
            continue
        where = clauses[2]
        leaves = [s for s in _walk(where) if not s.segments and not s.is_meta
                  and s.pos_marker and not s.is_type('whitespace', 'newline')]
        # Comparison operators can contain several raw tokens (>=, <>). Work
        # with the complete AST operator, never its individual characters.
        for operator in _walk(where):
            if not operator.is_type('comparison_operator') or not operator.pos_marker:
                continue
            if operator.raw not in ('=', '<', '>', '<=', '>=', '<>', '!=', '^='):
                continue
            a, b = operator.pos_marker.source_slice.start, operator.pos_marker.source_slice.stop
            previous = next((s for s in reversed(leaves) if s.pos_marker.source_slice.stop <= a), None)
            following = next((s for s in leaves if s.pos_marker.source_slice.start >= b), None)
            if previous is not None and not previous.is_type('comment', 'inline_comment', 'block_comment'):
                gap(previous.pos_marker.source_slice.stop, a, ' ')
            if following is not None and not following.is_type('comment', 'inline_comment', 'block_comment'):
                gap(b, following.pos_marker.source_slice.start, ' ')
    return edits


def _owned_walk(node):
    """Walk one query's expressions without entering descendant queries."""
    yield node
    for child in node.segments:
        if not child.is_type('select_statement'):
            yield from _owned_walk(child)


def nested_query_gap_edits(source, tree):
    """Prepare supported nested queries using AST context, not input columns.

    Return edits and statement indexes whose WHERE clauses this pass owns.
    All changes for one statement form a B2 atomic group. Expressions, comment
    bytes and literal bytes are never replaced. Existing comment/OR refusal
    for boolean restructuring is intentionally retained.
    """
    edits, handled = [], set()
    protected = protected_spans(source)
    statements = [s for s in tree.segments if s.is_type('statement')]
    for index, statement in enumerate(statements):
        root = next((s for s in statement.segments if s.is_type('select_statement')), None)
        if root is None:
            continue
        nodes = list(_walk(root))
        queries = [s for s in nodes if s.is_type('select_statement')]
        if len(queries) < 2 or any(s.is_type(
                'join_clause', 'over_clause', 'window_specification',
                'set_expression', 'with_compound_statement') for s in nodes):
            continue
        clauses_by_id = {}
        for query in queries:
            clauses = [s for s in query.segments if s.is_code and not s.is_meta]
            if [s.get_type() for s in clauses] not in (
                    ['select_clause', 'from_clause'],
                    ['select_clause', 'from_clause', 'where_clause']):
                break
            if sum(s.is_type('from_expression_element')
                   for s in _owned_walk(clauses[1])) != 1:
                break
            clauses_by_id[id(query)] = clauses
        if len(clauses_by_id) != len(queries):
            continue
        bracket_queries = {}

        def locate(node, bracket=None):
            if node.is_type('bracketed'):
                bracket = node
            if node.is_type('select_statement') and node is not root:
                if bracket is not None:
                    bracket_queries[id(bracket)] = node
            for child in node.segments:
                locate(child, bracket)

        locate(root)
        if len(bracket_queries) != len(queries) - 1:
            continue
        group = f'nested-select:{index}'
        handled.add(index)

        def gap(a, b, replacement):
            raw = source[a:b]
            if (not raw or raw.isspace()) and raw != replacement:
                edits.append(Edit(a, b, replacement, 'NESTED-GAPS', group, group))

        def boundary(a, b, replacement):
            # Preserve trailing versus leading comment attachment. Only touch
            # the whitespace between comment spans, never the comment itself.
            comments = [p for p in protected if a <= p.start and p.end <= b
                        and p.kind in ('line_comment', 'block_comment')]
            if not comments:
                gap(a, b, replacement)
                return
            points = [(a, comments[0].start)] + [
                (p.end, q.start) for p, q in zip(comments, comments[1:])
            ] + [(comments[-1].end, b)]
            if any(source[x:y].strip() or source[x:y].count('\n') > 1
                   for x, y in points):
                return  # Detached/ambiguous comments retain their placement.
            indent = replacement.rsplit('\n', 1)[-1]
            for position, (x, y) in enumerate(points):
                if position == 0 and '\n' not in source[x:y]:
                    continue  # A trailing comment stays on its original line.
                gap(x, y, replacement if position == 0 else '\n' + indent)

        def start(node):
            return node.pos_marker.source_slice.start

        def stop(node):
            return node.pos_marker.source_slice.stop

        def render(query, level):
            clauses = clauses_by_id[id(query)]
            base = ' ' * level
            for left, right in zip(clauses, clauses[1:]):
                boundary(stop(left), start(right),
                         ('\n' if right.is_type('from_clause') else '\n\n') + base)
            from_clause = clauses[1]
            keyword = next(s for s in from_clause.segments if s.is_type('keyword'))
            target = next(s for s in _owned_walk(from_clause)
                          if s.is_type('from_expression_element'))
            gap(stop(keyword), start(target), ' ')
            vertical = False
            if len(clauses) == 3:
                where = clauses[2]
                expression = next(s for s in where.segments if s.is_type('expression'))
                ands = [s for s in expression.segments
                        if s.is_type('binary_operator') and s.raw_upper == 'AND']
                vertical = bool(ands) and not any(
                    s.is_type('binary_operator') and s.raw_upper == 'OR'
                    for s in expression.segments)
                vertical = vertical and not any(s.is_type('comment') for s in _walk(where))
                leaves = [s for s in _owned_walk(expression)
                          if not s.segments and not s.is_meta and s.pos_marker
                          and not s.is_type('whitespace', 'newline')]
                prefix = []
                if ands:
                    prefix = [s.raw for s in leaves if stop(s) <= start(ands[0])]
                has_prefix = prefix == ['1', '=', '1']
                keyword = next(s for s in where.segments if s.is_type('keyword'))
                gap(stop(keyword), start(expression),
                    ' 1=1\n' + base + '    AND ' if vertical and not has_prefix else ' ')
                if vertical:
                    for operator in ands:
                        previous = next(s for s in reversed(leaves) if stop(s) <= start(operator))
                        following = next(s for s in leaves if start(s) >= stop(operator))
                        gap(stop(previous), start(operator), '\n' + base + '    ')
                        gap(stop(operator), start(following), ' ')
                for operator in _owned_walk(expression):
                    if not operator.is_type('comparison_operator') or operator.raw not in (
                            '=', '<', '>', '<=', '>=', '<>', '!=', '^='):
                        continue
                    spacing = '' if vertical and has_prefix and stop(operator) < start(ands[0]) else ' '
                    previous = next((s for s in reversed(leaves) if stop(s) <= start(operator)), None)
                    following = next((s for s in leaves if start(s) >= stop(operator)), None)
                    if previous is not None:
                        gap(stop(previous), start(operator), spacing)
                    if following is not None:
                        gap(stop(operator), start(following), spacing)
            for clause in clauses:
                container_level = level + (4 if clause.is_type('select_clause')
                                           or (clause.is_type('where_clause') and vertical) else 0)
                for bracket in _owned_walk(clause):
                    if not bracket.is_type('bracketed'):
                        continue
                    child = bracket_queries.get(id(bracket))
                    if child is None:
                        continue
                    opening = next(s for s in bracket.segments if s.is_type('start_bracket'))
                    closing = next(s for s in bracket.segments if s.is_type('end_bracket'))
                    boundary(stop(opening), start(child), '\n' + ' ' * (container_level + 4))
                    boundary(stop(child), start(closing), '\n' + ' ' * container_level)
                    render(child, container_level + 4)

        gap(source.rfind('\n', 0, start(root)) + 1, start(root), '')
        render(root, 0)
    return edits, handled
