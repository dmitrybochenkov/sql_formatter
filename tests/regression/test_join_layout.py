"""Regression coverage: join layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B42JoinTests(unittest.TestCase):
    def check_join(self, source, expected):
        from formatter import validate_sql_unchanged, sql_tokens
        diagnostics = []
        actual = format_sql(source, diagnostics=diagnostics)
        self.assertEqual(actual, expected)
        validate_sql_unchanged(source, actual)
        self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002') for d in diagnostics))
        second_diagnostics = []
        self.assertEqual(format_sql(actual, diagnostics=second_diagnostics), actual)
        self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002') for d in second_diagnostics))
        from formatter_modules.formatter_case import normalize_case
        self.assertEqual(sql_tokens(normalize_case(source)), sql_tokens(actual))
        return actual

    def test_literal_multiple_conditions_whitespace_variants(self):
        expected = "SELECT\n    t.id\n    , s.amount\nFROM users t\n\nINNER JOIN sales s\nON s.user_id = t.id\n    AND s.status = 'OK'\n    AND s.amount >= 10\n;\n"
        for source in (
            "SELECT t.id,s.amount FROM users t INNER JOIN sales s ON s.user_id=t.id AND s.status='OK' AND s.amount>=10;",
            "SELECT t.id, s.amount\nFROM users t\nINNER JOIN sales s\nON s.user_id=t.id\nAND s.status='OK'\nAND s.amount>=10;",
            "  SELECT t.id, s.amount\n    FROM users t\n      INNER JOIN sales s\n         ON s.user_id=t.id AND s.status='OK' AND s.amount>=10;",
        ):
            with self.subTest(source=source):
                self.check_join(source, expected)

    def test_single_condition_join_variants(self):
        for kind in ('JOIN', 'INNER JOIN', 'LEFT JOIN', 'LEFT OUTER JOIN', 'RIGHT JOIN', 'FULL OUTER JOIN'):
            with self.subTest(kind=kind):
                self.check_join(f'SELECT t.a FROM t {kind} u ON t.a=u.a;',
                                f'SELECT\n    t.a\nFROM t\n\n{kind} u\nON t.a = u.a\n;\n')

    def test_comment_above_join(self):
        for comment in ('-- payments', '/* payments */', '-- payments\n-- keep with JOIN'):
            for gap in ('\n', '\n\n', '\n\n\n'):
                with self.subTest(comment=comment, gap=gap):
                    self.check_join(f'SELECT t.a FROM t{gap}{comment}\nLEFT JOIN u ON t.a=u.a;',
                                    f'SELECT\n    t.a\nFROM t\n\n{comment}\nLEFT JOIN u\nON t.a = u.a\n;\n')

    def test_trailing_comments_keep_attachment(self):
        self.check_join('SELECT t.a FROM t -- table\nJOIN u ON t.a=u.a -- predicate\nAND u.b=2;',
                        'SELECT\n    t.a\nFROM t -- table\n\nJOIN u\nON t.a = u.a -- predicate\n    AND u.b = 2\n;\n')
        self.check_join('SELECT t.a FROM t JOIN -- target\n u ON t.a=u.a;',
                        'SELECT\n    t.a\nFROM t\n\nJOIN -- target\n u\nON t.a = u.a\n;\n')

    def test_multiple_joins_and_comment(self):
        self.check_join('SELECT t.a FROM t JOIN u ON t.a=u.a\n-- next\nJOIN v ON u.a=v.a;',
                        'SELECT\n    t.a\nFROM t\n\nJOIN u\nON t.a = u.a\n\n-- next\nJOIN v\nON u.a = v.a\n;\n')

    def test_literals_and_existing_keyword_case_preserved(self):
        self.check_join("SELECT t.a FROM t left join u on t.a=u.a and u.b='SELECT FROM WHERE JOIN AND';",
                        "SELECT\n    t.a\nFROM t\n\nLEFT JOIN u\nON t.a = u.a\n    AND u.b = 'SELECT FROM WHERE JOIN AND'\n;\n")

    def test_between_and_parenthesized_or(self):
        self.check_join('SELECT t.a FROM t JOIN u ON t.a=u.a AND u.b BETWEEN 1 AND 2 AND (u.c=3 OR u.c=4);',
                        'SELECT\n    t.a\nFROM t\n\nJOIN u\nON t.a = u.a\n    AND u.b BETWEEN 1 AND 2\n    AND (u.c = 3 OR u.c = 4)\n;\n')

    def test_where_group_order_remain_stable(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT t.a FROM t JOIN u ON t.a=u.a WHERE t.b=1 AND u.b=2 GROUP BY t.a ORDER BY t.a;'
        expected = 'SELECT\n    t.a\nFROM t\n\nJOIN u\nON t.a = u.a\n\nWHERE 1=1\n    AND t.b = 1\n    AND u.b = 2\n\nGROUP BY t.a\n\nORDER BY t.a\n;\n'
        actual = format_sql(source, diagnostics=[])
        self.assertEqual(actual, expected)
        validate_sql_unchanged(source, actual)
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)
        self.assertNotIn('ON 1=1', actual)

    def test_join_subqueries_and_window_queries_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('SELECT a FROM t JOIN (SELECT a FROM u) s ON t.a=s.a;',
                       'SELECT ROW_NUMBER() OVER (ORDER BY t.a) FROM t JOIN u ON t.a=u.a;',
                       'SELECT a FROM t JOIN u USING (a);'):
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                self.assertEqual(nested_query_gap_edits(source, tree, include_simple=True,
                                                       include_joins=True), ([], set()))

    def test_narrow_edits_atomic_and_order_independent(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits, apply_edits
        from formatter_modules.formatter_protection import protected_spans
        source = "SELECT t.a FROM t\n-- join\nJOIN u ON t.a=u.a AND u.b='OK';"
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits, owners = nested_query_gap_edits(source, tree, include_simple=True, include_joins=True)
        self.assertEqual(owners, {0})
        self.assertEqual(len({e.group_id for e in edits}), 1)
        self.assertTrue(all(not source[e.start:e.end].strip() for e in edits))
        spans = [(p.start, p.end) for p in protected_spans(source)]
        accepted, warnings = plan_edits(source, edits, protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(len(accepted), len(edits))
        reverse, warnings = plan_edits(source, list(reversed(edits)), protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(apply_edits(source, accepted), apply_edits(source, reverse))
        edit = next(e for e in edits if e.start < e.end)
        accepted, warnings = plan_edits(source, edits, protected=spans + [(edit.start, edit.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))

if __name__ == "__main__":
    unittest.main()
