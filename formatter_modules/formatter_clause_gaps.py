"""Conservative AST-anchored gap formatting for GROUP BY, ORDER BY, FROM.

Only direct commas are list separators. Expressions are never rewritten;
comment ownership is checked before proposing related gap edits.
"""
import re
from formatter_modules.formatter_edits import Edit
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans

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
    if kind == 'from_clause':
        rendered = title + ' ' + items[0]
        for item in items[1:]:
            rendered += '\n' + base + '    , ' + item
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


def commented_clause_gap_edits(source, clause, indent='    ', group=None):
    """Direct GROUP/ORDER separators only; return None before any partial edit.

    Expressions and ORDER modifiers are opaque. Comment ownership is inferred
    only from uninterrupted standalone chains or one trailing comment.
    """
    if not clause.is_type('groupby_clause', 'orderby_clause'):
        return None
    code = [s for s in clause.segments if s.is_code and not s.is_meta]
    if len(code) < 3:
        return None
    start = lambda s: s.pos_marker.source_slice.start
    stop = lambda s: s.pos_marker.source_slice.stop
    if group is None:
        group = f'comment-list:{start(clause)}:{stop(clause)}'
    comments = [p for p in protected_spans(source)
                if p.kind in ('line_comment', 'block_comment')]
    edits = []

    def propose(a, b, replacement):
        if source[a:b] != replacement:
            edits.append(Edit(a, b, replacement, 'COMMENT-CLAUSE-GAPS', clause.get_type(), group))

    def region(a, b, comma=None, header=False):
        spans = [p for p in comments if a <= p.start and p.end <= b]
        points = ([(a, spans[0].start)]
                  + [(p.end, q.start) for p, q in zip(spans, spans[1:])]
                  + [(spans[-1].end, b)]) if spans else [(a, b)]
        raw = []
        for x, y in points:
            text = source[x:y]
            if comma is not None and x <= start(comma) < stop(comma) <= y:
                text = source[x:start(comma)] + source[stop(comma):y]
            if text.strip():
                return False
            raw.append(text)
        if not spans:
            multiline = not header or any(s.is_type('comma') for s in code)
            propose(a, b, ('\n' + indent if multiline else ' ') + (', ' if comma else ''))
            return True
        trailing = '\n' not in raw[0]
        if trailing:
            # A trailing+standalone chain is deliberately not guessed.
            if header or len(spans) != 1 or raw[-1].count('\n') > 1:
                return False
            if spans[0].kind == 'line_comment' and '\n' not in raw[-1]:
                return False
        elif any(text.count('\n') != 1 for text in raw[1:]):
            return False
        for i, (x, y) in enumerate(points):
            replacement = ' ' if trailing and i == 0 else '\n' + indent
            if i == len(points) - 1 and comma is not None:
                replacement += ', '
            propose(x, y, replacement)
        return True

    # No keyword rewriting: preserve the spelling of GROUP, ORDER and BY.
    if source[stop(code[0]):start(code[1])].strip():
        return None
    propose(stop(code[0]), start(code[1]), ' ')
    if not region(stop(code[1]), start(code[2]), header=True):
        return None
    for i, node in enumerate(code[2:], 2):
        if node.is_type('comma'):
            if i == len(code) - 1 or not region(stop(code[i - 1]), start(code[i + 1]), node):
                return None
    return edits


def nested_query_gap_edits(source, tree, include_simple=False, include_joins=False, include_comment_lists=False, include_having=False, include_cte=False, include_sets=False):
    """Prepare supported queries using AST context, not input columns.

    Return edits and statement indexes whose WHERE clauses this pass owns.
    include_simple extends the same rules to flat queries and FROM lists,
    plus comment-free GROUP/ORDER lists and opaque HAVING boundaries;
    the default retains the B3.2 helper's supported scope.
    include_joins opts flat queries into ordinary, direct JOIN ... ON gaps.
    include_comment_lists enables atomic comment-aware GROUP/ORDER gaps;
    an ambiguous list is left opaque while safe query boundaries are handled.
    include_having enables HAVING predicates and their nested SELECT context.
    include_cte enables a top-level WITH container around the same query rules.
    include_sets enables AST set containers and their independent SELECT branches.
    All changes for one statement form a B2 atomic group. Expressions, comment
    bytes and literal bytes are never replaced. Existing comment/OR refusal
    for boolean restructuring is intentionally retained.
    """
    edits, handled = [], set()
    protected = protected_spans(source)
    statements = [s for s in tree.segments if s.is_type('statement')]
    for index, statement in enumerate(statements):
        root = next((s for s in statement.segments if s.is_type('select_statement')), None)
        if root is None and include_sets:
            root = next((s for s in statement.segments if s.is_type('set_expression')), None)
        if root is None and include_cte:
            root = next((s for s in statement.segments if s.is_type('with_compound_statement')), None)
        if root is None:
            continue
        cte_mode = root.is_type('with_compound_statement')
        query_types = ('select_statement', 'set_expression') if include_sets else ('select_statement',)
        set_mode = include_sets and any(s.is_type('set_expression') for s in _walk(root))
        ctes, cte_commas, main_query = [], [], None
        if cte_mode:
            code = [s for s in root.segments if s.is_code and not s.is_meta]
            ctes = [s for s in code if s.is_type('common_table_expression')]
            cte_commas = [s for s in code if s.is_type('comma')]
            mains = [s for s in code if s.is_type(*query_types)]
            if (not ctes or len(mains) != 1 or len(cte_commas) != len(ctes) - 1
                    or any(s is not code[0] and not s.is_type(
                        'common_table_expression', 'comma', *query_types) for s in code)):
                continue
            if any(not any(s.is_type('bracketed') and any(
                    child.is_type(*query_types) for child in s.segments)
                    for s in cte.segments) for cte in ctes):
                continue
            main_query = mains[0]
        nodes = list(_walk(root))
        queries = [s for s in nodes if s.is_type('select_statement')]
        joins = [s for s in nodes if s.is_type('join_clause')]
        if joins and (not include_joins or not include_simple):
            continue
        if (len(queries) < 2 and not include_simple) or any(s.is_type(
                'over_clause', 'window_specification') or (s.is_type('set_expression') and not include_sets) or (s is not root and s.is_type('with_compound_statement')) for s in nodes):
            continue
        # Only ordinary JOIN ... ON is owned here; USING and other forms
        # retain their existing fallback. Never claim a JOIN with a subquery.
        if any(any(s.is_type('select_statement') for s in _walk(join))
               or not any(s.is_type('join_on_condition') for s in join.segments)
               for join in joins):
            continue
        clauses_by_id = {}
        for query in queries:
            clauses = [s for s in query.segments if s.is_code and not s.is_meta]
            by_type = {s.get_type(): s for s in clauses}
            allowed = {'select_clause', 'from_clause', 'where_clause'}
            if include_simple and (cte_mode or set_mode or len(queries) == 1 or (include_having and 'having_clause' in by_type)):
                allowed |= {'groupby_clause', 'orderby_clause', 'having_clause'}
            if (len(by_type) != len(clauses) or not set(by_type) <= allowed
                    or 'select_clause' not in by_type
                    or (not (cte_mode or set_mode) and 'from_clause' not in by_type)):
                break
            # Preserve the helper's previous scope unless explicitly enabled.
            if not include_comment_lists and any(s.is_type('comment') for clause in clauses
                   if clause.is_type('groupby_clause', 'orderby_clause') for s in _walk(clause)):
                break
            if ('from_clause' in by_type and sum(s.is_type('from_expression_element')
                    for s in _owned_walk(by_type['from_clause'])) != 1
                    and not (include_simple and (cte_mode or set_mode or len(queries) == 1 or (joins and query is root)))):
                break
            clauses_by_id[id(query)] = clauses
        if len(clauses_by_id) != len(queries):
            continue
        if joins:
            direct_joins = []
            for query in (queries if cte_mode or set_mode else [root]):
                from_clause = next((s for s in clauses_by_id[id(query)] if s.is_type('from_clause')), None)
                if from_clause is None:
                    continue
                local_joins = [s for expr in from_clause.segments if expr.is_type('from_expression')
                               for s in expr.segments if s.is_type('join_clause')]
                if local_joins and any(s.is_type('select_statement') for s in _walk(from_clause)):
                    break  # Derived targets remain outside ordinary JOIN support.
                direct_joins.extend(local_joins)
            if {id(s) for s in joins} != {id(s) for s in direct_joins}:
                continue  # Parenthesized JOIN trees are outside this pass.
        bracket_queries = {}

        def locate(node, bracket=None):
            if node.is_type('bracketed'):
                bracket = node
            if node.is_type(*query_types):
                if bracket is not None:
                    bracket_queries[id(bracket)] = node
                # Branches of a set belong to that set, not its outer bracket.
                # Expression wrappers around scalar SELECTs remain transparent.
                bracket = None
            for child in node.segments:
                locate(child, bracket)

        locate(root)
        if not set_mode and len(bracket_queries) != len(queries) - 1:
            continue
        # Only alternating AST branches/operators, with an optional global ORDER.
        # Unsupported tails and wrappers remain outside this atomic pass.
        valid_sets = True
        for node in (s for s in nodes if s.is_type('set_expression')):
            parts = [s for s in node.segments if s.is_code and not s.is_meta]
            if parts and parts[-1].is_type('orderby_clause'):
                parts = parts[:-1]
            if len(parts) < 3 or len(parts) % 2 == 0:
                valid_sets = False
                break
            for i, part in enumerate(parts):
                if i % 2:
                    valid = part.is_type('set_operator') and [s.raw_upper for s in part.segments
                        if s.is_code and not s.is_meta] in (
                        ['UNION'], ['UNION', 'ALL'], ['UNION', 'DISTINCT'],
                        ['INTERSECT'], ['INTERSECT', 'ALL'], ['EXCEPT'], ['EXCEPT', 'ALL'])
                else:
                    valid = part.is_type(*query_types) or (
                        part.is_type('bracketed') and id(part) in bracket_queries)
                if not valid:
                    valid_sets = False
        if not valid_sets:
            continue
        group = f'nested-select:{index}'
        handled.add(index)

        def gap(a, b, replacement):
            raw = source[a:b]
            if (not raw or raw.isspace()) and raw != replacement:
                # B2 correctly rejects an insertion at a replacement's start.
                # A compact `(select` needs one combined header edit instead.
                if a == b:
                    for i, edit in enumerate(edits):
                        if (edit.group_id == group and edit.rule_id == 'CLAUSE-CASE'
                                and edit.start == a
                                and edit.replacement == source[edit.start:edit.end].upper()):
                            edits[i] = Edit(a, edit.end, replacement + edit.replacement,
                                            'CLAUSE-CASE', group, group)
                            return
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

        def join_boundary(a, b, replacement):
            comments = [p for p in protected if a <= p.start and p.end <= b
                        and p.kind in ('line_comment', 'block_comment')]
            if not comments:
                gap(a, b, replacement)
                return
            if '\n' not in replacement:
                return  # Never collapse a line comment's terminating newline.
            points = [(a, comments[0].start)] + [
                (p.end, q.start) for p, q in zip(comments, comments[1:])
            ] + [(comments[-1].end, b)]
            if any(source[x:y].strip() for x, y in points):
                return
            # A blank below a comment makes its attachment ambiguous.
            if any(source[x:y].count('\n') > 1 for x, y in points[1:]):
                return
            indent = replacement.rsplit('\n', 1)[-1]
            trailing = '\n' not in source[points[0][0]:points[0][1]]
            for position, (x, y) in enumerate(points):
                if position == 0 and trailing:
                    continue
                gap(x, y, replacement if position == (1 if trailing else 0)
                    else '\n' + indent)

        def render_joins(from_clause, base):
            for from_expression in from_clause.segments:
                if not from_expression.is_type('from_expression'):
                    continue
                previous = None
                for node in from_expression.segments:
                    if node.is_type('from_expression_element'):
                        previous = node
                    elif node.is_type('join_clause'):
                        if previous is not None:
                            join_boundary(stop(previous), start(node), '\n\n' + base)
                        code = [s for s in node.segments if s.is_code and not s.is_meta]
                        for left, right in zip(code, code[1:]):
                            join_boundary(stop(left), start(right),
                                          '\n' + base if right.is_type('join_on_condition') else ' ')
                        on = next(s for s in code if s.is_type('join_on_condition'))
                        keyword = next(s for s in on.segments if s.is_type('keyword'))
                        expression = next(s for s in on.segments if s.is_type('expression'))
                        gap(stop(keyword), start(expression), ' ')
                        leaves = [s for s in _owned_walk(expression) if not s.segments
                                  and not s.is_meta and s.pos_marker
                                  and not s.is_type('whitespace', 'newline')]
                        vertical = not any(s.is_type('binary_operator') and s.raw_upper == 'OR'
                                           for s in expression.segments)
                        for operator in _owned_walk(expression):
                            is_and = (vertical and operator in expression.segments
                                      and operator.is_type('binary_operator') and operator.raw_upper == 'AND')
                            if not is_and and not (operator.is_type('comparison_operator') and operator.raw in (
                                    '=', '<', '>', '<=', '>=', '<>', '!=', '^=')):
                                continue
                            before = next((s for s in reversed(leaves) if stop(s) <= start(operator)), None)
                            after = next((s for s in leaves if start(s) >= stop(operator)), None)
                            if before is not None and (is_and or not before.is_type('comment')):
                                gap(stop(before), start(operator), '\n' + base + '    ' if is_and else ' ')
                            if after is not None and not after.is_type('comment'):
                                gap(stop(operator), start(after), ' ')
                        previous = node

        def owned_brackets(node):
            # A set container, like a SELECT, owns its descendants. Visiting
            # its bracketed branches here again would duplicate atomic edits.
            for child in node.segments:
                if child.is_type(*query_types):
                    continue
                if child.is_type('bracketed'):
                    yield child
                yield from owned_brackets(child)

        def render(query, level):
            if query.is_type('bracketed'):
                child = bracket_queries[id(query)]
                opening = next(s for s in query.segments if s.is_type('start_bracket'))
                closing = next(s for s in query.segments if s.is_type('end_bracket'))
                boundary(stop(opening), start(child), '\n' + ' ' * (level + 4))
                boundary(stop(child), start(closing), '\n' + ' ' * level)
                render(child, level + 4)
                return
            if query.is_type('set_expression'):
                parts = [s for s in query.segments if s.is_code and not s.is_meta]
                for left, right in zip(parts, parts[1:]):
                    join_boundary(stop(left), start(right), '\n\n' + ' ' * level)
                for part in parts:
                    if part.is_type('set_operator'):
                        keywords = [s for s in part.segments if s.is_code and not s.is_meta]
                        for left, right in zip(keywords, keywords[1:]):
                            gap(stop(left), start(right), ' ')
                    elif part.is_type('orderby_clause'):
                        candidates = commented_clause_gap_edits(source, part, ' ' * (level + 4), group)
                        if candidates is not None:
                            edits.extend(candidates)
                    else:
                        render(part, level)
                return
            clauses = clauses_by_id[id(query)]
            by_type = {s.get_type(): s for s in clauses}
            base = ' ' * level
            for clause in clauses:
                keyword = next(s for s in clause.segments if s.is_type('keyword'))
                if keyword.raw_upper in ('SELECT', 'FROM', 'WHERE') and keyword.raw != keyword.raw_upper:
                    for i, edit in enumerate(edits):
                        if (edit.group_id == group and edit.rule_id == 'NESTED-GAPS'
                                and edit.start == edit.end == start(keyword)):
                            edits[i] = Edit(start(keyword), stop(keyword), edit.replacement + keyword.raw_upper,
                                            'CLAUSE-CASE', group, group)
                            break
                    else:
                        edits.append(Edit(start(keyword), stop(keyword), keyword.raw_upper,
                                          'CLAUSE-CASE', group, group))
            for left, right in zip(clauses, clauses[1:]):
                # Use comment-aware gaps only for supported block boundaries;
                # nested brackets retain their existing attachment rules.
                clause_gap = boundary if len(queries) > 1 else gap
                if ((include_comment_lists and right.is_type('groupby_clause', 'orderby_clause'))
                        or (include_having and right.is_type('having_clause'))
                        or right.is_type('where_clause')):
                    clause_gap = join_boundary
                clause_gap(stop(left), start(right),
                           ('\n' if right.is_type('from_clause') else '\n\n') + base)
            from_clause = by_type.get('from_clause')
            if from_clause is not None:
                keyword = next(s for s in from_clause.segments if s.is_type('keyword'))
                target = next(s for s in _owned_walk(from_clause)
                              if s.is_type('from_expression_element'))
                gap(stop(keyword), start(target), ' ')
                if joins:
                    render_joins(from_clause, base)
                # Direct FROM expressions only: commas inside expressions are not
                # table separators. Keep the first target beside its header.
                targets = [s for s in from_clause.segments if s.is_type('from_expression')]
                commas = [s for s in from_clause.segments if s.is_type('comma')]
                if len(targets) > 1 and len(commas) == len(targets) - 1:
                    for left, comma, right in zip(targets, commas, targets[1:]):
                        gap(stop(left), start(comma), '\n' + base + '    ')
                        gap(stop(comma), start(right), ' ')
            for clause in clauses:
                if clause.is_type('groupby_clause', 'orderby_clause') and include_comment_lists:
                    candidates = commented_clause_gap_edits(source, clause, base + '    ', group)
                    if candidates is not None:
                        edits.extend(candidates)
                    continue  # A refused list has no partial or legacy edits.
                if clause.is_type('groupby_clause', 'orderby_clause'):
                    # Direct AST commas delimit complete items, including
                    # ORDER modifiers. Function arguments are never split.
                    code = [s for s in clause.segments if s.is_code and not s.is_meta]
                    first_keyword, second_keyword = code[:2]
                    items = code[2:]
                    commas = [s for s in items if s.is_type('comma')]
                    gap(stop(first_keyword), start(second_keyword), ' ')
                    if items:
                        gap(stop(second_keyword), start(items[0]),
                            '\n' + base + '    ' if commas else ' ')
                    for i, item in enumerate(items):
                        if item.is_type('comma') and 0 < i < len(items) - 1:
                            gap(stop(items[i - 1]), start(item), '\n' + base + '    ')
                            gap(stop(item), start(items[i + 1]), ' ')
                # HAVING uses its separate comparison-only handler below.
                # GROUP/ORDER expressions stay opaque.
                if not clause.is_type('select_clause', 'from_clause', 'where_clause'):
                    continue
                leaves = [s for s in _owned_walk(clause) if not s.segments
                          and not s.is_meta and s.pos_marker
                          and not s.is_type('whitespace', 'newline')]
                for operator in _owned_walk(clause):
                    if not (operator.is_type('binary_operator') and operator.raw in ('+', '-', '*', '/', '%', '||')):
                        continue
                    previous = next((s for s in reversed(leaves) if stop(s) <= start(operator)), None)
                    following = next((s for s in leaves if start(s) >= stop(operator)), None)
                    if previous is not None and not previous.is_type('comment'):
                        gap(stop(previous), start(operator), ' ')
                    if following is not None and not following.is_type('comment'):
                        gap(stop(operator), start(following), ' ')
            vertical = False
            where = by_type.get('where_clause')
            if where is not None:
                keyword = next(s for s in where.segments if s.is_type('keyword'))
                expression = next(s for s in where.segments
                                  if s.is_code and not s.is_meta and s is not keyword)
                ands = [s for s in expression.segments
                        if expression.is_type('expression')
                        and s.is_type('binary_operator') and s.raw_upper == 'AND']
                vertical = bool(ands) and not any(
                    s.is_type('binary_operator') and s.raw_upper == 'OR'
                    for s in expression.segments)
                # Only this WHERE's comments can affect its restructuring.
                # Child SELECTs own their own predicates and comments.
                owned_comments = {s.pos_marker.source_slice.start for s in _owned_walk(where)
                                  if s.is_type('comment') and s.pos_marker}
                vertical = vertical and not any(p.start in owned_comments
                                               for p in ambiguous_comment_spans(source))
                vertical = vertical and not source[stop(keyword):start(expression)].strip()
                leaves = [s for s in _owned_walk(expression)
                          if not s.segments and not s.is_meta and s.pos_marker
                          and not s.is_type('whitespace', 'newline')]
                prefix = []
                code_leaves = [s for s in leaves if not s.is_type('comment')]
                if ands:
                    prefix = [s.raw for s in code_leaves if stop(s) <= start(ands[0])]
                has_prefix = prefix == ['1', '=', '1']
                gap(stop(keyword), start(expression),
                    ' 1=1\n' + base + '    AND ' if vertical and not has_prefix else ' ')
                if vertical:
                    for operator in ands:
                        previous = next(s for s in reversed(code_leaves) if stop(s) <= start(operator))
                        following = next(s for s in leaves if start(s) >= stop(operator))
                        join_boundary(stop(previous), start(operator), '\n' + base + '    ')
                        if not following.is_type('comment'):
                            gap(stop(operator), start(following), ' ')
                for operator in _owned_walk(expression):
                    if not operator.is_type('comparison_operator') or operator.raw not in (
                            '=', '<', '>', '<=', '>=', '<>', '!=', '^='):
                        continue
                    spacing = '' if vertical and has_prefix and stop(operator) < start(ands[0]) else ' '
                    previous = next((s for s in reversed(leaves) if stop(s) <= start(operator)), None)
                    following = next((s for s in leaves if start(s) >= stop(operator)), None)
                    if previous is not None and not previous.is_type('comment'):
                        gap(stop(previous), start(operator), spacing)
                    if following is not None and not following.is_type('comment'):
                        gap(stop(operator), start(following), spacing)
            having_vertical = False
            having = by_type.get('having_clause')
            if include_having and having is not None:
                keyword = next(s for s in having.segments if s.is_type('keyword'))
                predicate = next(s for s in having.segments
                                 if s.is_code and not s.is_meta and s is not keyword)
                # A bracketed predicate is one condition, even when it has ANDs.
                ands = [s for s in predicate.segments if predicate.is_type('expression')
                        and s.is_type('binary_operator') and s.raw_upper == 'AND']
                having_vertical = bool(ands) and not any(
                    s.is_type('binary_operator') and s.raw_upper == 'OR'
                    for s in predicate.segments)
                # Detached comments retain their attachment. Header comments
                # are handled through separate gaps, never a broad replacement.
                having_vertical = having_vertical and not any(
                    start(having) <= p.start < stop(having) for p in ambiguous_comment_spans(source))
                leaves = [s for s in _owned_walk(predicate) if not s.segments
                          and not s.is_meta and s.pos_marker
                          and not s.is_type('whitespace', 'newline')]
                code_leaves = [s for s in leaves if not s.is_type('comment')]
                has_prefix = bool(ands) and [s.raw for s in code_leaves
                                             if stop(s) <= start(ands[0])] == ['1', '=', '1']
                header_comments = [p for p in protected
                                   if stop(keyword) <= p.start and p.end <= start(predicate)
                                   and p.kind in ('line_comment', 'block_comment')]
                if having_vertical and not has_prefix and header_comments:
                    points = [(stop(keyword), header_comments[0].start)] + [
                        (p.end, q.start) for p, q in zip(header_comments, header_comments[1:])
                    ] + [(header_comments[-1].end, start(predicate))]
                    for i, (a, b) in enumerate(points):
                        if i == 0:
                            gap(a, b, ' 1=1' + (' ' if '\n' not in source[a:b]
                                                else '\n' + base + '    '))
                        else:
                            gap(a, b, '\n' + base + '    ' + ('AND ' if i == len(points) - 1 else ''))
                else:
                    gap(stop(keyword), start(predicate),
                        ' 1=1\n' + base + '    AND ' if having_vertical and not has_prefix else ' ')
                if having_vertical:
                    for operator in ands:
                        previous = next(s for s in reversed(code_leaves) if stop(s) <= start(operator))
                        following = next(s for s in leaves if start(s) >= stop(operator))
                        join_boundary(stop(previous), start(operator), '\n' + base + '    ')
                        if not following.is_type('comment'):
                            gap(stop(operator), start(following), ' ')
                for operator in _owned_walk(predicate):
                    if not operator.is_type('comparison_operator') or operator.raw not in (
                            '=', '<', '>', '<=', '>=', '<>', '!=', '^='):
                        continue
                    spacing = '' if having_vertical and has_prefix and stop(operator) < start(ands[0]) else ' '
                    previous = next((s for s in reversed(leaves) if stop(s) <= start(operator)), None)
                    following = next((s for s in leaves if start(s) >= stop(operator)), None)
                    if previous is not None and not previous.is_type('comment'):
                        gap(stop(previous), start(operator), spacing)
                    if following is not None and not following.is_type('comment'):
                        gap(stop(operator), start(following), spacing)
            for clause in clauses:
                container_level = level + (4 if clause.is_type('select_clause')
                                           or (clause.is_type('where_clause') and vertical)
                                           or (clause.is_type('having_clause') and having_vertical) else 0)
                for bracket in owned_brackets(clause):
                    child = bracket_queries.get(id(bracket))
                    if child is None:
                        continue
                    opening = next(s for s in bracket.segments if s.is_type('start_bracket'))
                    closing = next(s for s in bracket.segments if s.is_type('end_bracket'))
                    boundary(stop(opening), start(child), '\n' + ' ' * (container_level + 4))
                    boundary(stop(child), start(closing), '\n' + ' ' * container_level)
                    render(child, container_level + 4)

        gap(source.rfind('\n', 0, start(root)) + 1, start(root), '')
        if cte_mode:
            keyword = next(s for s in root.segments if s.is_type('keyword'))
            gap(stop(keyword), start(ctes[0]), ' ')
            for cte in ctes:
                header = [s for s in cte.segments if s.is_code and not s.is_meta]
                bracket = next(s for s in header if s.is_type('bracketed'))
                child = bracket_queries[id(bracket)]
                for left, right in zip(header, header[1:]):
                    if not right.is_type('cte_column_list'):
                        gap(stop(left), start(right), ' ')
                opening = next(s for s in bracket.segments if s.is_type('start_bracket'))
                closing = next(s for s in bracket.segments if s.is_type('end_bracket'))
                boundary(stop(opening), start(child), '\n    ')
                boundary(stop(child), start(closing), '\n')
                render(child, 4)
            for left, comma, right in zip(ctes, cte_commas, ctes[1:]):
                a, b = stop(left), start(right)
                comments = [p for p in protected if a <= p.start and p.end <= b
                            and p.kind in ('line_comment', 'block_comment')]
                points = ([(a, comments[0].start)] + [
                    (p.end, q.start) for p, q in zip(comments, comments[1:])
                ] + [(comments[-1].end, b)]) if comments else [(a, b)]
                raw = [source[x:start(comma)] + source[stop(comma):y]
                       if x <= start(comma) < stop(comma) <= y else source[x:y] for x, y in points]
                if any(t.strip() for t in raw):
                    continue
                trailing = bool(comments) and '\n' not in raw[0]
                if comments and (any(t.count('\n') != 1 for t in raw[1:])
                                 or (trailing and len(comments) != 1)):
                    continue  # Keep an ambiguous separator and its comments intact.
                for i, (x, y) in enumerate(points):
                    if not comments:
                        replacement = '\n\n, '
                    elif i == 0:
                        replacement = ' ' if trailing else '\n\n'
                    elif i == len(points) - 1:
                        replacement = '\n\n, ' if trailing else '\n, '
                    else:
                        replacement = '\n'
                    if source[x:y] != replacement:
                        edits.append(Edit(x, y, replacement, 'CTE-GAPS', group, group))
            join_boundary(stop(ctes[-1]), start(main_query), '\n\n')
            render(main_query, 0)
        else:
            render(root, 0)
    return edits, handled
