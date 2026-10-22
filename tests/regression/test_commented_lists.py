"""Regression coverage: commented lists. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B43CommentedClauseTests(unittest.TestCase):
    def check_list(self, clause, body, expected_body):
        from formatter import validate_sql_unchanged, sql_tokens
        from formatter_modules.formatter_protection import protected_spans
        source = 'SELECT a,b FROM t ' + clause + ' ' + body + ';'
        expected = 'SELECT\n    a\n    , b\nFROM t\n\n' + clause + '\n    ' + expected_body + '\n;\n'
        diagnostics = []
        actual = format_sql(source, diagnostics=diagnostics)
        self.assertEqual(actual, expected)
        self.assertEqual(diagnostics, [])
        second_diagnostics = []
        self.assertEqual(format_sql(actual, diagnostics=second_diagnostics), actual)
        self.assertEqual(second_diagnostics, [])
        validate_sql_unchanged(source, actual)
        self.assertEqual(sql_tokens(source), sql_tokens(actual))
        def protected(sql):
            return [(p.kind, sql[p.start:p.end]) for p in protected_spans(sql)]
        self.assertEqual(protected(source), protected(actual))
        return actual

    def test_standalone_comments_and_leading_commas(self):
        for clause in ('GROUP BY', 'ORDER BY'):
            for body in ('a,\n-- next\nb', 'a\n-- next\n, b', ' a,\n  -- next\n    b'):
                with self.subTest(clause=clause, body=body):
                    self.check_list(clause, body, 'a\n    -- next\n    , b')

    def test_trailing_line_comments(self):
        for clause in ('GROUP BY', 'ORDER BY'):
            for body in ('a, -- left\nb', 'a -- left\n, b'):
                with self.subTest(clause=clause, body=body):
                    self.check_list(clause, body, 'a -- left\n    , b')

    def test_comment_chain_and_multiline_bytes(self):
        for clause in ('GROUP BY', 'ORDER BY'):
            self.check_list(clause, 'a,\n-- one\n/* two\n  unchanged , */\nb',
                            'a\n    -- one\n    /* two\n  unchanged , */\n    , b')

    def test_inline_block_one_line_and_multiline_input(self):
        for clause in ('GROUP BY', 'ORDER BY'):
            for body in ('a, /* left */ b', 'a, /* left */\nb', 'a /* left */\n, b'):
                with self.subTest(clause=clause, body=body):
                    self.check_list(clause, body, 'a /* left */\n    , b')

    def test_expressions_literals_and_modifiers_opaque(self):
        self.check_list('ORDER BY', "COALESCE(a,b) DESC NULLS LAST,\n-- next\nCOALESCE(c,'x,y') ASC",
                        "COALESCE(a,b) DESC NULLS LAST\n    -- next\n    , COALESCE(c,'x,y') ASC")
        self.check_list('GROUP BY', "COALESCE(a,b),\n-- next\nCOALESCE(c,'x,y')",
                        "COALESCE(a,b)\n    -- next\n    , COALESCE(c,'x,y')")

    def test_header_and_final_comments(self):
        for clause in ('GROUP BY', 'ORDER BY'):
            self.check_list(clause, '\n-- first\na,\n-- second\nb -- last\n',
                            '-- first\n    a\n    -- second\n    , b -- last')
        source = 'SELECT a,b FROM t GROUP BY a,\n-- next\nb -- last\nORDER BY a,b;'
        expected = 'SELECT\n    a\n    , b\nFROM t\n\nGROUP BY\n    a\n    -- next\n    , b -- last\n\nORDER BY\n    a\n    , b\n;\n'
        self.assertEqual(format_sql(source, diagnostics=[]), expected)
        self.assertEqual(format_sql(expected, diagnostics=[]), expected)

    def test_ambiguous_and_mixed_chains_refuse_entire_list(self):
        from formatter import walk, validate_sql_unchanged
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import commented_clause_gap_edits
        for kind, header in (('groupby_clause', 'GROUP BY'), ('orderby_clause', 'ORDER BY')):
            for body in ('a,b,\n-- detached\n\nc', 'a,b, -- left\n-- next\nc',
                         'a,b,\n/* detached */\n\nc'):
                with self.subTest(kind=kind, body=body):
                    source = 'SELECT a FROM t ' + header + ' ' + body + ';'
                    def node(sql):
                        return next(s for s in walk(Linter(dialect='teradata').parse_string(sql).tree) if s.is_type(kind))
                    original = node(source)
                    self.assertIsNone(commented_clause_gap_edits(source, original, group='test'))
                    diagnostics = []
                    actual = format_sql(source, diagnostics=diagnostics)
                    self.assertEqual(node(actual).raw, original.raw)
                    self.assertTrue(any(d.code == 'SQLFMT-C001' for d in diagnostics))
                    validate_sql_unchanged(source, actual)
                    self.assertEqual(format_sql(actual, diagnostics=[]), actual)

    def test_atomicity_protection_conflicts_and_order(self):
        from sqlfluff.core import Linter
        from formatter import walk
        from formatter_modules.formatter_clause_gaps import commented_clause_gap_edits
        from formatter_modules.formatter_edits import Edit, plan_edits, apply_edits
        from formatter_modules.formatter_protection import protected_spans
        source = 'SELECT a FROM t ORDER BY a,\n-- next\nb;'
        node = next(s for s in walk(Linter(dialect='teradata').parse_string(source).tree) if s.is_type('orderby_clause'))
        edits = commented_clause_gap_edits(source, node, group='list')
        spans = [(p.start, p.end) for p in protected_spans(source)]
        accepted, warnings = plan_edits(source, edits, protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(len(accepted), len(edits))
        reverse, warnings = plan_edits(source, list(reversed(edits)), protected=spans)
        self.assertEqual(apply_edits(source, accepted), apply_edits(source, reverse))
        for e in edits:
            accepted, warnings = plan_edits(source, edits, protected=spans + [(e.start, e.end)])
            self.assertEqual(accepted, [])
            self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))
        e = max(edits, key=lambda e: e.end - e.start)
        conflict = Edit(e.start, e.start, ' ', 'TEST')
        accepted, warnings = plan_edits(source, [conflict] + edits, protected=spans)
        self.assertFalse(any(e.group_id == 'list' for e in accepted))
        self.assertTrue(any(d.code == 'SQLFMT-E001' for d in warnings))

    def test_query_group_integration_and_future_scope(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('SELECT ROW_NUMBER() OVER (ORDER BY a,\n-- next\nb) FROM t;',
                       'SELECT a FROM t JOIN (SELECT a FROM u) s ON t.a=s.a ORDER BY a,\n-- next\nb;',
                       'WITH q AS (SELECT a FROM t) SELECT a FROM q ORDER BY a,\n-- next\nb;'):
            tree = Linter(dialect='teradata').parse_string(source).tree
            result = nested_query_gap_edits(source, tree, include_simple=True,
                             include_joins=True, include_comment_lists=True)
            if 'JOIN (' in source:
                self.assertEqual(result[1], {0})
                self.assertTrue(result[0])
            else:
                self.assertEqual(result, ([], set()))

    def test_join_where_and_both_lists(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT t.a,u.b FROM t JOIN u ON t.a=u.a WHERE t.a=1 AND u.b=2 GROUP BY t.a,\n-- group\nu.b ORDER BY t.a,\n-- order\nu.b DESC;'
        expected = 'SELECT\n    t.a\n    , u.b\nFROM t\n\nJOIN u\nON t.a = u.a\n\nWHERE 1=1\n    AND t.a = 1\n    AND u.b = 2\n\nGROUP BY\n    t.a\n    -- group\n    , u.b\n\nORDER BY\n    t.a\n    -- order\n    , u.b DESC\n;\n'
        diagnostics = []
        actual = format_sql(source, diagnostics=diagnostics)
        self.assertEqual(actual, expected)
        self.assertEqual(diagnostics, [])
        validate_sql_unchanged(source, actual)
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)

if __name__ == "__main__":
    unittest.main()
