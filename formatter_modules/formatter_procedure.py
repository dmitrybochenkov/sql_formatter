"""Atomic procedure layout using the shared grammar and existing DML formatter."""
from difflib import SequenceMatcher

from formatter_modules.formatter_edits import Edit, Diagnostic, apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans
from formatter_modules.formatter_runtime import source_linter, normalize_external_newlines
from formatter_modules.formatter_case import normalize_case


class ProcedureRefusal(ValueError):
    def __init__(self, code='SQLFMT-E003'):
        self.code = code
        super().__init__('Procedure cannot be formatted atomically')


def walk(node):
    yield node
    for child in node.segments:
        yield from walk(child)


def code(node):
    return [s for s in node.segments if s.is_code and not s.is_meta]


def start(node):
    return node.pos_marker.source_slice.start


def stop(node):
    return node.pos_marker.source_slice.stop


def indented_fragment(text, level):
    """Indent continuation lines, never the interior of a protected unit."""
    spans = protected_spans(text)
    inserts = [i + 1 for i, ch in enumerate(text) if ch == '\n' and i + 1 < len(text)
               and text[i + 1] != '\n' and not any(p.start <= i < p.end for p in spans)]
    for i in reversed(inserts):
        text = text[:i] + ' ' * level + text[i:]
    return text


def format_procedure(source, format_dml, validate, diagnostics, *, _checking=False):
    """Transaction boundary: never expose a partial procedure or exception text."""
    original = source
    bom = '\ufeff' if source.startswith('\ufeff') else ''
    source = source[len(bom):]
    try:
        source = normalize_external_newlines(source)
        parsed = source_linter().parse_string(source)
        if (parsed.tree is None or parsed.violations or
                any(s.is_type('unparsable') for s in walk(parsed.tree))):
            raise ProcedureRefusal()
        from formatter_modules.formatter_clause_gaps import window_specification_parts
        if any(n.is_type('over_clause') and window_specification_parts(n) is None
               for n in walk(parsed.tree)):
            raise ProcedureRefusal('SQLFMT-E004')
        if ambiguous_comment_spans(source):
            raise ProcedureRefusal('SQLFMT-C001')
        definitions = [s for s in parsed.tree.segments if s.is_type('procedure_definition')]
        if len(definitions) != 1:
            raise ProcedureRefusal()
        protected = protected_spans(source)
        edits = []

        def edit(a, b, text):
            if source[a:b] != text:
                edits.append(Edit(a, b, text, 'PROCEDURE', 'procedure', 'procedure'))

        def gap(a, b, text):
            if source[a:b].strip():
                raise ProcedureRefusal('SQLFMT-C001')
            edit(a, b, text)

        def boundary(a, b, text):
            comments = [p for p in protected if a <= p.start and p.end <= b
                        and p.kind in ('line_comment', 'block_comment')]
            if not comments:
                gap(a, b, text)
                return
            if '\n' not in text:
                # Inline comments stay in place; never move tokens past --.
                return
            indent = text.rsplit('\n', 1)[-1]
            points = [(a, comments[0].start)] + [(p.end, q.start)
                for p, q in zip(comments, comments[1:])] + [(comments[-1].end, b)]
            for i, (x, y) in enumerate(points):
                raw = source[x:y]
                if raw.strip() or (i > 0 and raw.count('\n') > 1):
                    raise ProcedureRefusal('SQLFMT-C001')
                if i == 0 and '\n' not in raw:
                    continue  # Keep a trailing comment attached to its predecessor.
                gap(x, y, text if i == 0 else '\n' + indent)

        def operators(node):
            leaves = [s for s in walk(node) if not s.segments and s.is_code and not s.is_meta]
            for op in walk(node):
                if not (op.is_type('comparison_operator') or
                        (op.is_type('binary_operator') and op.raw in ('+', '-', '*', '/', '%', '||'))):
                    continue
                before = next((s for s in reversed(leaves) if stop(s) <= start(op)), None)
                after = next((s for s in leaves if start(s) >= stop(op)), None)
                if before is not None:
                    boundary(stop(before), start(op), ' ')
                if after is not None:
                    boundary(stop(op), start(after), ' ')

        def items(bracket, level):
            # Moving a trailing comma across an argument comment could change
            # attachment. Until a proven list policy exists, refuse the procedure.
            if any(start(bracket) < p.start < stop(bracket)
                   and p.kind in ('line_comment', 'block_comment') for p in protected):
                raise ProcedureRefusal('SQLFMT-C001')
            parts = code(bracket)
            opening, closing = parts[0], parts[-1]
            values = parts[1:-1]
            for value in values:
                if value.is_type('procedure_parameter'):
                    for left, right in zip(code(value), code(value)[1:]):
                        boundary(stop(left), start(right), ' ')
            if not values:
                boundary(stop(opening), start(closing), '')
                return
            boundary(stop(opening), start(values[0]), '\n' + ' ' * (level + 4))
            for left, right in zip(values, values[1:]):
                boundary(stop(left), start(right), '\n' + ' ' * (level + 4)
                         if right.is_type('comma') else ' ')
            boundary(stop(values[-1]), start(closing), '\n' + ' ' * level)

        def kind(unit):
            return code(unit)[0].get_type() if unit.is_type('procedure_executable') else unit.get_type()

        def body_units(units, opening, closing, level):
            previous = opening
            previous_kind = None
            for unit in units:
                if unit.is_type('statement_terminator'):
                    boundary(stop(previous), start(unit), '')
                else:
                    current = kind(unit)
                    blank = previous_kind is not None and not (
                        previous_kind == current and current in ('procedure_declaration', 'procedure_assignment'))
                    boundary(stop(previous), start(unit), ('\n\n' if blank else '\n') + ' ' * (level + 4))
                    render(unit, level + 4)
                    previous_kind = current
                previous = unit
            boundary(stop(previous), start(closing), '\n' + ' ' * level)

        def dml(node, level):
            ds = []
            candidate = format_dml(node.raw + ';', diagnostics=ds)
            if ds:
                diagnostics.extend(ds)
                raise ProcedureRefusal('SQLFMT-E004' if any(d.code == 'SQLFMT-E004' for d in ds) else 'SQLFMT-E003')
            tree = source_linter().parse_string(candidate).tree
            stmt = next((s for s in tree.segments if s.is_type('statement')), None)
            result = next((s for s in stmt.segments if s.is_type(node.get_type())), None) if stmt else None
            if result is None:
                raise ProcedureRefusal()
            text = indented_fragment(result.raw, level)
            # DML's existing AST renderer has already validated its result.
            # Transfer only changed ranges, still protected and atomic as a whole.
            for tag, a, b, c, d in SequenceMatcher(None, node.raw, text, autojunk=False).get_opcodes():
                if tag != 'equal':
                    edit(start(node) + a, start(node) + b, text[c:d])

        def render(node, level):
            parts = code(node)
            if node.is_type('procedure_definition'):
                verb, keyword, name, params = parts[:4]
                boundary(0, start(verb), '\n' if source[:start(verb)].strip() else '')
                boundary(stop(verb), start(keyword), ' ')
                boundary(stop(keyword), start(name), ' ')
                boundary(stop(name), start(params), '')
                items(params, 0)
                previous = params
                for part in parts[4:]:
                    boundary(stop(previous), start(part), '\n')
                    if part.is_type('procedure_security'):
                        for left, right in zip(code(part), code(part)[1:]):
                            boundary(stop(left), start(right), ' ')
                    else:
                        render(part, 0)
                    previous = part
            elif node.is_type('procedure_block'):
                body_units(parts[1:-1], parts[0], parts[-1], level)
            elif node.is_type('procedure_while'):
                keyword, condition, do = parts[:3]
                boundary(stop(keyword), start(condition), ' ')
                boundary(stop(condition), start(do), ' ')
                operators(condition)
                body_units(parts[3:-2], do, parts[-2], level)
                boundary(stop(parts[-2]), start(parts[-1]), ' ')
            elif node.is_type('procedure_executable'):
                if len(parts) != 2 or not parts[-1].is_type('statement_terminator'):
                    raise ProcedureRefusal()
                render(parts[0], level)
                boundary(stop(parts[0]), start(parts[1]),
                         '\n' + ' ' * level if parts[0].is_type('insert_statement', 'delete_statement') else '')
            elif node.is_type('insert_statement', 'delete_statement'):
                dml(node, level)
            elif node.is_type('procedure_call'):
                boundary(stop(parts[0]), start(parts[1]), ' ')
                boundary(stop(parts[1]), start(parts[2]), '')
                items(parts[2], level)
            elif node.is_type('procedure_assignment', 'procedure_declaration'):
                for left, right in zip(parts, parts[1:]):
                    boundary(stop(left), start(right), '' if right.is_type('comma') else ' ')
                for part in parts:
                    if part.is_type('expression'):
                        operators(part)
            else:
                raise ProcedureRefusal()

        definition = definitions[0]
        render(definition, 0)
        end = next(s for s in parsed.tree.segments if s.is_type('statement_terminator'))
        boundary(stop(definition), start(end), '')
        # Preserve a final comment; ensure a terminating LF only outside it.
        if source[stop(end):].strip():
            if not source.endswith('\n'):
                edit(len(source), len(source), '\n')
        else:
            gap(stop(end), len(source), '\n')
        planned, warnings = plan_edits(source, edits, protected=[(p.start, p.end) for p in protected])
        if warnings or len(planned) != len(edits):
            diagnostics.extend(warnings)
            raise ProcedureRefusal()
        result = apply_edits(source, planned)
        result = normalize_case(result)
        validate(original[len(bom):], result)
        candidate = bom + result
        if not _checking:
            repeat_diagnostics = []
            repeated = format_procedure(candidate, format_dml, validate, repeat_diagnostics, _checking=True)
            if repeated != candidate or repeat_diagnostics:
                diagnostics.extend(repeat_diagnostics)
                raise ProcedureRefusal()
        return candidate
    except Exception as exc:
        code_value = exc.code if isinstance(exc, ProcedureRefusal) else 'SQLFMT-E003'
        diagnostics.append(Diagnostic(code_value, 1, 'Процедура сохранена целиком: безопасное форматирование не подтверждено'))
        return original
