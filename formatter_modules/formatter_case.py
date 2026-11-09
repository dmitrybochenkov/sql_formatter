"""SQLFluff CP01–CP05 proposals, applied only through the atomic edit planner."""
from sqlfluff.core import Linter

from formatter_modules.formatter_edits import Edit, apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans
from formatter_modules.formatter_runtime import SourceMap
from formatter_modules.formatter_dialect import select_config

from formatter_modules.formatter_request import proof_memo

RULES = ('CP01', 'CP02', 'CP03', 'CP04', 'CP05')


def _tokens(tree):
    """Full AST ancestry and ordinal, independent of whitespace and comments."""
    result = []
    def visit(node, path):
        if node.is_meta or node.is_type('whitespace', 'newline', 'end_of_file', 'comment'):
            return
        here = path + (node.get_type(),)
        if node.segments:
            index = 0
            for child in node.segments:
                if child.is_meta or child.is_type('whitespace', 'newline', 'end_of_file', 'comment'):
                    continue
                visit(child, here + (index,))
                index += 1
        else:
            result.append((here, node.raw, node.pos_marker.source_slice))
    visit(tree, ())
    return result


@proof_memo()
def normalize_case(source):
    from formatter_modules.sqlfluff_config_adapter import build_config, active_rules, RULE_SETTINGS
    from formatter_modules.formatter_config import current_settings
    enabled = active_rules()
    if not enabled:
        return source
    config = build_config(case=True)
    config = select_config(source, config)
    linter = Linter(config=config)
    pack = linter.get_rulepack()
    if {r.code for r in pack.rules} != set(enabled):
        raise ValueError('Unexpected case rule pack')
    mapping = SourceMap.build(source)
    def parse(text):
        parsed = linter.parse_rendered(linter.render_string(text, '<case>', config.copy(), 'utf-8'))
        if parsed.tree is None or parsed.violations or parsed.tree.raw != text:
            raise ValueError('Ambiguous case-normalization AST')
        return parsed
    parsed = parse(mapping.normalized)
    before = _tokens(parsed.tree)
    leaves = {(s.start, s.stop): (path, raw) for path, raw, s in before}
    if len(leaves) != len(before):
        raise ValueError('Ambiguous token source ranges')
    linted = linter.lint_parsed(parsed, pack, fix=False)
    edits = {}
    for violation in linted.violations:
        code = violation.rule_code()
        if code not in enabled:
            raise ValueError('Unexpected case diagnostic')
        for fix in violation.fixes:
            anchor = fix.anchor
            span = anchor.pos_marker.source_slice
            old = mapping.normalized[span]
            replacement = ''.join(segment.raw for segment in fix.edit)
            leaf = leaves.get((span.start, span.stop))
            policy = current_settings().get('case', RULE_SETTINGS[code][0])
            target = old.lower() if policy == 'lower' else old.upper()
            if (fix.edit_type != 'replace' or anchor.segments or not leaf
                    or leaf[0][-1] != anchor.get_type()
                    or leaf[1] != old or anchor.raw != old or replacement != target
                    or len(replacement) != len(old) or old == replacement
                    or any(c.isspace() for c in old)):
                raise ValueError('Non-token or ambiguous case fix')
            edit = mapping.original_edit(Edit(span.start, span.stop, replacement, code,
                                               'case-normalization', 'case-normalization'))
            key = (edit.start, edit.end)
            if key in edits and edits[key].replacement != replacement:
                raise ValueError('Conflicting case proposals')
            edits[key] = edit
    planned, warnings = plan_edits(source, list(edits.values()), protected=[
        (s.start, s.end) for s in protected_spans(source)])
    if warnings or len(planned) != len(edits):
        raise ValueError('Case group rejected')
    candidate = apply_edits(source, planned)
    if not planned:
        return source
    after = _tokens(parse(SourceMap.build(candidate).normalized).tree)
    expected = {key: e.replacement for key, e in edits.items()}
    if len(before) != len(after):
        raise ValueError('Case normalization changed token count')
    for (path, raw, span), (new_path, new_raw, _) in zip(before, after):
        original = mapping.original_slice(span)
        if path != new_path or new_raw != expected.get((original.start, original.stop), raw):
            raise ValueError('Case normalization changed token ownership')
    return candidate
