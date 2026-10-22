"""Regression coverage: edit safety. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B2SafetyTests(unittest.TestCase):
    def test_cr_inputs_preserve_protected_bytes_on_both_calls(self):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        cases = [
            ("SELECT id,\r\n name FROM users;", "SELECT\n    id\n    , name\nFROM users\n;\n"),
            ("SELECT 'first\r\n  last' AS txt FROM t;", "SELECT\n    'first\r\n  last' AS txt\nFROM t\n;\n"),
            ("SELECT 'first\rlast' AS txt FROM t;", "SELECT\n    'first\rlast' AS txt\nFROM t\n;\n"),
            ("SELECT a -- keep\r\nFROM t;\r\n", "SELECT\n    a -- keep\nFROM t\n;\n"),
            ("SELECT /* keep\r\n  comment */ a FROM t;", "SELECT /* keep\r\n  comment */ a\nFROM t\n;\n"),
            ("SELECT a\nFROM t\rWHERE a=1;", "SELECT\n    a\nFROM t\n\nWHERE a = 1\n;\n"),
            ("SELECT a FROM t;\r", "SELECT\n    a\nFROM t\n;\n"),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                first_diagnostics, second_diagnostics = [], []
                first = format_sql(source, diagnostics=first_diagnostics)
                second = format_sql(first, diagnostics=second_diagnostics)
                self.assertEqual(first, expected)
                self.assertEqual(second.encode('utf-8'), first.encode('utf-8'))
                validate_sql_unchanged(source, first)
                self.assertEqual([(p.kind, source[p.start:p.end]) for p in protected_spans(source)],
                                 [(p.kind, first[p.start:p.end]) for p in protected_spans(first)])
                self.assertFalse(any(d.code == 'SQLFMT-E003' for d in first_diagnostics + second_diagnostics))

    def test_cr_formatting_keeps_stdout_clean(self):
        import contextlib
        import io
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(format_sql('SELECT a FROM t;\r\n'), 'SELECT\n    a\nFROM t\n;\n')
        self.assertEqual(output.getvalue(), '')
        self.assertEqual(errors.getvalue(), '')

    def test_nested_select_overlap_is_stable_and_preserves_sql(self):
        from formatter import sql_tokens, validate_sql_unchanged, remove_formatter_where_prefix
        cases = [
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x,y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT\n    x\n    , y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x FROM u WHERE b=2 AND x IN (\nSELECT y,z FROM v\n)\n);",
        ]
        # B3.2: explicitly approved replacement of the B2 fallback output.
        expected = (
            'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n'
            '    AND id IN (\n        SELECT\n            x\n            , y\n'
            '        FROM u\n    )\n;\n'
        )
        deeper_expected = (
            'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n'
            '    AND id IN (\n        SELECT\n            x\n        FROM u\n\n'
            '        WHERE 1=1\n            AND b = 2\n            AND x IN (\n'
            '                SELECT\n                    y\n                    , z\n'
            '                FROM v\n            )\n    )\n;\n'
        )
        for index, source in enumerate(cases):
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                second = format_sql(first, diagnostics=[])
                self.assertEqual(first, second)
                before, before_comments = sql_tokens(source)
                after, after_comments = sql_tokens(first)
                self.assertEqual(remove_formatter_where_prefix(before),
                                 remove_formatter_where_prefix(after))
                self.assertEqual(before_comments, after_comments)
                validate_sql_unchanged(source, first)
                self.assertEqual(first, expected if index < 2 else deeper_expected)
                self.assertFalse(any(d.code == 'SQLFMT-E001' for d in warnings))

    def test_nested_query_with_literals_and_comments_is_preserved(self):
        from formatter import sql_tokens, validate_sql_unchanged, remove_formatter_where_prefix
        source = ("SELECT id FROM t WHERE a=1 AND id IN (\n"
                  "SELECT 'a  b' AS x, -- keep\n y FROM u\n);")
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(first, format_sql(first, diagnostics=[]))
        validate_sql_unchanged(source, first)
        before, before_comments = sql_tokens(source)
        after, after_comments = sql_tokens(first)
        self.assertEqual(before, remove_formatter_where_prefix(after))
        self.assertEqual(before_comments, after_comments)
        self.assertIn("'a  b'", first)
        self.assertIn('-- keep', first)
        # B4.5: child comments no longer block the eligible outer WHERE.

    def test_ast_edits_retain_rule_and_atomic_group(self):
        from unittest.mock import patch
        from formatter_modules.formatter_edits import plan_edits
        with patch('formatter.plan_edits', wraps=plan_edits) as planner:
            format_sql("SELECT a, -- keep\n b FROM t;", diagnostics=[])
        edits = planner.call_args.args[1]
        comment_edits = [e for e in edits if e.rule_id == 'COMMENT-LIST']
        self.assertGreaterEqual(len(comment_edits), 3)
        self.assertEqual(len({e.group_id for e in comment_edits}), 1)
        self.assertIsNotNone(comment_edits[0].group_id)
        self.assertIn('select_clause', comment_edits[0].group_id)
        self.assertTrue(all(e.owner for e in comment_edits))

    def test_select_word_in_literal_is_not_a_nested_query(self):
        source = "SELECT 'SELECT x FROM y' AS txt FROM t;"
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(first, format_sql(first, diagnostics=[]))
        self.assertEqual(first, "SELECT\n    'SELECT x FROM y' AS txt\nFROM t\n;\n")
        self.assertFalse(any('дочерний SELECT' in d.message for d in warnings))

if __name__ == "__main__":
    unittest.main()
