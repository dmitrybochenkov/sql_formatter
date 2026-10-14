"""Conservative bridge for legacy whole-text formatting passes.

A legacy pass proposes a new string. Changes are mapped back to the current
source and rejected when they touch protected lexical spans. This is a
transitional adapter, not a replacement for AST-scoped edits.
"""
from difflib import SequenceMatcher
from formatter_modules.formatter_edits import Edit, Diagnostic, apply_edits, line_number, plan_edits
from formatter_modules.formatter_protection import ambiguous_comment_spans, protected_spans


def guarded_pass(source: str, transform, rule_id: str):
    proposed = transform(source)
    if proposed == source:
        return source, []
    protected = [(s.start, s.end) for s in protected_spans(source)]
    # Include the whitespace between a detached comment and the next token.
    for s in ambiguous_comment_spans(source):
        end = s.end
        while end < len(source) and source[end] in ' \t\r\n':
            end += 1
        protected.append((s.start, end))
    edits = []
    for tag, a, b, c, d in SequenceMatcher(None, source, proposed, autojunk=False).get_opcodes():
        if tag != 'equal':
            edits.append(Edit(a, b, proposed[c:d], rule_id, 'legacy-postprocess'))
    accepted, warnings = plan_edits(source, edits, protected)
    # A zero-width insertion inside a protected span must also be rejected.
    filtered = []
    for e in accepted:
        if e.start == e.end and any(start < e.start < end for start, end in protected):
            warnings.append(Diagnostic('SQLFMT-E002', line_number(source, e.start),
                                       f'Вставка {rule_id} внутри защищённого участка; пропущена'))
        else:
            filtered.append(e)
    return apply_edits(source, filtered), warnings
