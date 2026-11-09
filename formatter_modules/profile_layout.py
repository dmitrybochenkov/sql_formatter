"""Non-default style gaps on AST-owned lists/boundaries, never expression text.

One atomic edit group per list/boundary; ambiguous comments remain opaque.
Original GROUP boundaries are paired by AST traversal and checked item counts.
"""
from formatter_modules.formatter_config import current_settings
from formatter_modules.formatter_edits import Edit, plan_edits, apply_edits
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans
from formatter_modules.formatter_runtime import source_linter

NAMES = {'select_clause': 'select', 'from_clause': 'from',
         'groupby_clause': 'group_by', 'orderby_clause': 'order_by',
         'where_clause': 'where', 'having_clause': 'having',
         'qualify_clause': 'qualify', 'join_clause': 'join'}
DEFAULT_BLANKS = frozenset(('join', 'where', 'group_by', 'having', 'qualify', 'order_by'))


def nodes(tree, window=False):
    window = window or tree.is_type('over_clause', 'window_specification')
    if not window:
        yield tree
        for child in tree.segments:
            yield from nodes(child, window)


def bounds(node):
    span = node.pos_marker.source_slice
    return span.start, span.stop


def parts(clause):
    code = [s for s in clause.segments if s.is_code and not s.is_meta]
    name = NAMES.get(clause.get_type())
    if name == 'select':
        items = [s for s in code if s.is_type('select_clause_element')]
        if not items:
            return None
        header_end = max(bounds(s)[1] for s in code if bounds(s)[1] <= bounds(items[0])[0])
    elif name == 'from':
        items = [s for s in code if s.is_type('from_expression')]
        if not items:
            return None
        header_end = bounds(code[0])[1]
    elif name in ('group_by', 'order_by'):
        if len(code) < 3:
            return None
        header_end = bounds(code[1])[1]
        # Each direct comma delimits a whole expression including sort modifiers.
        items = []
        start = None
        stop = None
        for s in code[2:]:
            if s.is_type('comma'):
                if start is None:
                    return None
                items.append((start, stop)); start = None
            else:
                if start is None:
                    start = bounds(s)[0]
                stop = bounds(s)[1]
        if start is not None:
            items.append((start, stop))
    else:
        return None
    if name in ('select', 'from'):
        items = [bounds(s) for s in items]
    commas = [bounds(s) for s in code if s.is_type('comma')]
    if len(commas) != len(items) - 1:
        return None
    return header_end, items, commas


def apply_profile_layout(source, original):
    settings = current_settings()
    comma_names = [name for name in ('select', 'from', 'group_by', 'order_by')
                   if settings.get('commas', name) != 'leading']
    layout = settings.get('group_by', 'layout')
    blanks = frozenset(settings.get('spacing', 'blank_line_before'))
    if not comma_names and layout == 'multiline' and blanks == DEFAULT_BLANKS:
        return source, []
    tree = source_linter().parse_string(source).tree
    if tree is None:
        raise ValueError('Profile layout requires AST')
    all_nodes = list(nodes(tree))
    protected = protected_spans(source)
    ambiguous = ambiguous_comment_spans(source)
    original_groups = []
    if layout == 'preserve':
        original_tree = source_linter().parse_string(original).tree
        original_groups = [n for n in nodes(original_tree) if n.is_type('groupby_clause')]
    group_index = 0
    edits, diagnostics = [], []

    def add(target, a, b, replacement, group):
        if source[a:b] != replacement:
            target.append(Edit(a, b, replacement, 'PROFILE-LAYOUT', group, group))

    def gap(target, a, b, replacement, group, comma=None, comment_indent='    '):
        """Safe relocation of one direct separator across attached comments."""
        comments = [p for p in protected if a <= p.start and p.end <= b
                    and p.kind in ('line_comment', 'block_comment')]
        points = ([(a, comments[0].start)] + [(x.end, y.start) for x, y in zip(comments, comments[1:])]
                  + [(comments[-1].end, b)]) if comments else [(a, b)]
        raw = []
        for x, y in points:
            fragment = source[x:y]
            if comma is not None and x <= comma[0] < comma[1] <= y:
                fragment = source[x:comma[0]] + source[comma[1]:y]
            if fragment.strip():
                return False
            raw.append(fragment)
        if not comments:
            add(target, a, b, replacement, group)
            return True
        if any(a <= p.start < b for p in ambiguous):
            return False
        trailing = '\n' not in raw[0]
        if trailing and len(comments) > 1:
            return False
        if any(t.count('\n') != 1 for t in raw[1:]):
            return False
        # Inline requests retain comment-required line breaks. Neither protected
        # newline nor the attachment of a standalone comment may be collapsed.
        indent = replacement.rsplit('\n', 1)[-1].replace(', ', '')
        if not indent.isspace():
            indent = comment_indent
        leading = replacement.startswith('\n') and replacement.endswith(', ')
        trailing_comma = replacement.startswith(',')
        for i, (x, y) in enumerate(points):
            value = ' ' if trailing and i == 0 else '\n' + indent
            if i == 0 and trailing_comma:
                value = ',' + value
            if i == len(points) - 1 and leading:
                value += ', '
            add(target, x, y, value, group)
        return True

    for clause in all_nodes:
        name = NAMES.get(clause.get_type())
        original_parts = None
        if name == 'group_by' and layout == 'preserve':
            if group_index >= len(original_groups):
                raise ValueError('GROUP BY ownership mismatch')
            original_parts = parts(original_groups[group_index]); group_index += 1
        if name not in comma_names and not (name == 'group_by' and layout != 'multiline'):
            continue
        data = parts(clause)
        if data is None:
            continue
        header, items, commas = data
        a, b = bounds(clause)
        base = source[source.rfind('\n', 0, a) + 1:a]
        if base.strip():
            continue
        indent = base + '    '
        group = f'profile-list:{a}:{b}'
        local = []
        breaks = [name == 'select' or (name != 'from' and len(items) > 1)] + [True] * len(commas)
        if name == 'group_by':
            if layout == 'inline':
                breaks = [False] * len(items)
            elif layout == 'preserve':
                if original_parts is None or len(original_parts[1]) != len(items):
                    raise ValueError('GROUP BY list mismatch')
                oh, oi, oc = original_parts
                breaks = ['\n' in original[oh:oi[0][0]] or '\r' in original[oh:oi[0][0]]]
                breaks += [any(c in original[left[1]:right[0]] for c in '\r\n')
                           for left, right in zip(oi, oi[1:])]
        okay = gap(local, header, items[0][0], '\n' + indent if breaks[0] else ' ', group, comment_indent=indent)
        for i, (left, comma, right) in enumerate(zip(items, commas, items[1:])):
            if not breaks[i + 1]:
                replacement = ', '
            elif settings.get('commas', name) == 'trailing':
                replacement = ',\n' + indent
            else:
                replacement = '\n' + indent + ', '
            okay = gap(local, left[1], right[0], replacement, group, comma, comment_indent=indent) and okay
        if okay:
            edits.extend(local)
        else:
            from formatter_modules.formatter_edits import Diagnostic
            diagnostics.append(Diagnostic('SQLFMT-C001', clause.pos_marker.line_no,
                                          'Неоднозначные комментарии списка: настройки раскладки не применены'))

    # Only direct clause boundaries and direct JOIN siblings; no window ORDER.
    for parent in all_nodes:
        children = [s for s in parent.segments if s.is_code and not s.is_meta]
        for left, right in zip(children, children[1:]):
            name = NAMES.get(right.get_type())
            if name not in DEFAULT_BLANKS | {'from'} or (name in blanks) == (name in DEFAULT_BLANKS):
                continue
            a, b = bounds(left)[1], bounds(right)[0]
            indent = source[source.rfind('\n', 0, b) + 1:b]
            if indent.strip():
                continue
            replacement = ('\n\n' if name in blanks else '\n') + indent
            group = f'profile-boundary:{a}:{b}'
            comments = [p for p in protected if a <= p.start and p.end <= b]
            if not comments:
                if not source[a:b].strip():
                    add(edits, a, b, replacement, group)
            else:
                # Blank above a leading comment belongs to its following block.
                # Trailing comments retain the left owner; adjust after them.
                first, last = comments[0], comments[-1]
                if any(a <= p.start < b for p in ambiguous):
                    continue
                if '\n' in source[a:first.start] and not source[a:first.start].strip():
                    add(edits, a, first.start, replacement, group)
                elif not source[last.end:b].strip() and '\n' in source[last.end:b]:
                    add(edits, last.end, b, replacement, group)
    planned, warnings = plan_edits(source, edits, protected=[(p.start, p.end) for p in protected])
    return apply_edits(source, planned), diagnostics + warnings
