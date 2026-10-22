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

    # Header may contain standalone comments immediately above the first item.
    first = positions[0][0]
    prefix = source[start:first]
    first_comments = [p for p in comments if p.start < first and p.end > start]
    if first_comments:
        if not _standalone_chain(source, first_comments, start, first):
            return None
        before_comment = source[start:first_comments[0].start]
        match = re.fullmatch(r'(?is)(\s*SELECT\b(?:[ \t]+(?:DISTINCT|ALL|TOP[ \t]+\d+))*)[ \t]*\n[ \t]*', before_comment)
        if match is None:
            return None
        header = ' '.join(match.group(1).split())
        edits.append(Edit(start, first_comments[0].start, header + '\n' + indent,
                          'COMMENT-LIST', 'select-header-comment'))
        _indent_comment_chain(source, first_comments, first, indent, edits)
    else:
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
        # A trailing comma before standalone comments belongs to the next
        # field's delimiter. Move it through whitespace-only atomic edits.
        if (all(ce <= p.start for p in gap_comments)
                and not before.strip()
                and re.fullmatch(r'[ \t]*\n[ \t]*', source[ce:gap_comments[0].start])
                and _standalone_chain(source, gap_comments, ce, right)):
            edits.append(Edit(left, gap_comments[0].start, '\n' + indent,
                              'COMMENT-LIST', 'remove-comma-before-comment'))
            _indent_comment_chain(source, gap_comments, right, indent, edits)
            # The last helper edit has this exact end range. Replace it so
            # the comma insertion cannot conflict with a whitespace edit.
            last = gap_comments[-1]
            edits = [e for e in edits if not (e.start == last.end and e.end == right)]
            edits.append(Edit(last.end, right, '\n' + indent + ', ',
                              'COMMENT-LIST', 'comma-after-standalone-comments'))
            continue
        # Standalone comments immediately above the next item, with a
        # leading comma before the item, are unambiguously attached to it.
        if (cs > left and ce <= right and
                all(p.end <= cs for p in gap_comments) and
                _standalone_chain(source, gap_comments, left, cs) and
                re.fullmatch(r'[ \t]*', source[ce:right])):
            first_comment = gap_comments[0]
            # The whitespace after the preceding field must contain a newline.
            before_comment = source[left:first_comment.start]
            if not re.fullmatch(r'[ \t]*\n[ \t]*', before_comment):
                return None
            edits.append(Edit(left, first_comment.start, '\n' + indent,
                              'COMMENT-LIST', 'before-item-comment'))
            _indent_comment_chain(source, gap_comments, cs, indent, edits)
            if source[ce:right] != ' ':
                edits.append(Edit(ce, right, ' ', 'COMMENT-LIST', 'after-leading-comma'))
            continue
        # Other comment layouts remain unsupported, rather than guessed.
        return None
    return edits


def _standalone_chain(source, comments, start, stop):
    """Comments separated by exactly one newline, no blank lines."""
    if not comments:
        return False
    for i, comment in enumerate(comments):
        line_start = source.rfind('\n', 0, comment.start) + 1
        if source[line_start:comment.start].strip():
            return False
        next_start = comments[i + 1].start if i + 1 < len(comments) else stop
        tail = source[comment.end:next_start]
        if not re.fullmatch(r'\n[ \t]*', tail):
            return False
    return True


def _indent_comment_chain(source, comments, stop, indent, edits):
    """Normalize only whitespace between comments, not comment bytes."""
    for i, comment in enumerate(comments):
        next_start = comments[i + 1].start if i + 1 < len(comments) else stop
        desired = '\n' + indent if i + 1 < len(comments) else '\n' + indent + (', ' if source[stop:stop+1] == ',' else '')
        # Last comma belongs to the gap logic, not to this helper.
        if i + 1 == len(comments):
            desired = '\n' + indent
        if source[comment.end:next_start] != desired:
            edits.append(Edit(comment.end, next_start, desired,
                              'COMMENT-LIST', 'between-item-comments'))
