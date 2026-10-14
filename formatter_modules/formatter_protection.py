"""Conservative lexical protection for SQL comments and quoted literals.

Spans are offsets into the original input. SQL comments are recognized only
outside quoted literals; doubled quote escapes are respected. Unterminated
constructs protect the remainder of the input.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ProtectedSpan:
    start: int
    end: int
    kind: str


def protected_spans(sql: str) -> list[ProtectedSpan]:
    spans = []
    i = 0
    n = len(sql)
    while i < n:
        start = i
        if sql.startswith('--', i):
            ends = [end for end in (sql.find('\r', i), sql.find('\n', i)) if end >= 0]
            i = min(ends) if ends else n
            spans.append(ProtectedSpan(start, i, 'line_comment'))
        elif sql.startswith('/*', i):
            end = sql.find('*/', i + 2)
            i = n if end < 0 else end + 2
            spans.append(ProtectedSpan(start, i, 'block_comment'))
        elif sql[i] in ("'", '"'):
            quote = sql[i]
            i += 1
            while i < n:
                if sql[i] == quote:
                    if i + 1 < n and sql[i + 1] == quote:
                        i += 2
                    else:
                        i += 1
                        break
                else:
                    i += 1
            spans.append(ProtectedSpan(start, i, 'literal' if quote == "'" else 'quoted_identifier'))
        else:
            i += 1
    return spans


def ambiguous_comment_spans(sql: str) -> list[ProtectedSpan]:
    """Conservative detection: detached line comments with a blank line below.

    The whole comment and adjacent whitespace is protected. This is only a
    diagnostic hint; it does not infer semantic ownership.
    """
    spans = protected_spans(sql)
    result = []
    for span in spans:
        if span.kind not in ('line_comment', 'block_comment'):
            continue
        line_start = sql.rfind('\n', 0, span.start) + 1
        if sql[line_start:span.start].strip():
            continue  # trailing comment on SQL expression
        tail = sql[span.end:]
        if tail.startswith('\n\n') or (tail.startswith('\n') and tail[1:].strip(' \t').startswith('\n')):
            result.append(span)
    return result
