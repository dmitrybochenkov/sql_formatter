"""AST-positioned, conservative SELECT list formatting with standalone comments.

Only whitespace and delimiter gaps are edited; comments and expressions are
never rewritten. Unsupported layouts return None for the legacy fallback.
"""
import re
from formatter_modules.formatter_edits import Edit
from formatter_modules.formatter_protection import protected_spans


def commented_select_edits(source, clause):
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
    line_start = source.rfind('\n', 0, start) + 1
    base = source[line_start:start]
    if base.strip() or '\t' in base:
        return None
    indent = base + '    '
    spans = protected_spans(source)
    comments = [p for p in spans if p.kind in ('line_comment', 'block_comment')]
    edits = []

    # Header and first item: no comments in this range for now.
    first = positions[0][0]
    prefix = source[start:first]
    if any(p.start < first and p.end > start for p in comments):
        return None
    if not re.fullmatch(r'(?is)\s*SELECT\b(?:\s+\w+)*\s*', prefix):
        return None
    header = ' '.join(prefix.split())
    desired = header + '\n' + indent
    if prefix != desired:
        edits.append(Edit(start, first, desired, 'COMMENT-LIST', 'select-header'))

    for i, comma in enumerate(commas):
        left, right = positions[i][1], positions[i+1][0]
        cs, ce = comma.pos_marker.source_slice.start, comma.pos_marker.source_slice.stop
        if not (left <= cs < ce <= right):
            return None
        before, after = source[left:cs], source[ce:right]
        gap_comments = [p for p in comments if p.start < right and p.end > left]
        if not gap_comments:
            if not before.isspace() and before != '':
                return None
            if not after.isspace() and after != '':
                return None
            if source[left:right] != '\n' + indent + ', ':
                edits.append(Edit(left, right, '\n' + indent + ', ', 'COMMENT-LIST', 'select-gap'))
            continue
        # Supported inline comment: `a, -- note\n b` -> `a -- note\n , b`.
        # Move only the delimiter, never the comment or expression bytes.
        if len(gap_comments) == 1 and gap_comments[0].kind == 'line_comment':
            comment = gap_comments[0]
            if (cs < comment.start < comment.end < right
                    and re.fullmatch(r'\s*', before)
                    and re.fullmatch(r'[ \t]*', source[ce:comment.start])
                    and source[comment.start:comment.end].startswith('--')
                    and re.fullmatch(r'\n[ \t]*', source[comment.end:right])):
                # No newline before the comment: it belongs to the left field.
                if '\n' not in source[ce:comment.start] and '\n' not in before:
                    edits.append(Edit(cs, ce, '', 'COMMENT-LIST', 'remove-trailing-comma'))
                    edits.append(Edit(comment.end, right, '\n' + indent + ', ',
                                      'COMMENT-LIST', 'leading-comma-after-comment'))
                    continue
        # Other comment layouts remain unsupported, rather than guessed.
        return None
    return edits
