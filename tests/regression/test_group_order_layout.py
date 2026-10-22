"""Regression coverage: group order layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B41ClauseContextTests(unittest.TestCase):
    GROUP_ORDER = 'SELECT\n    a\n    , b\nFROM t\n\nGROUP BY\n    a\n    , b\n\nORDER BY\n    a DESC\n    , b\n;\n'
    CASES = [
        ('SELECT a,b FROM t GROUP BY a,b ORDER BY a DESC,b;', GROUP_ORDER),
        ('SELECT a FROM t GROUP BY a;', 'SELECT\n    a\nFROM t\n\nGROUP BY a\n;\n'),
        ('SELECT a FROM t ORDER BY a;', 'SELECT\n    a\nFROM t\n\nORDER BY a\n;\n'),
        ('SELECT a,b FROM t,u GROUP BY a,b ORDER BY a DESC,b;',
         GROUP_ORDER.replace('FROM t\n', 'FROM t\n    , u\n')),
        ("SELECT a,b FROM t,u WHERE a=1 AND b='x' GROUP BY a,b ORDER BY a DESC,b;",
         GROUP_ORDER.replace('FROM t\n', "FROM t\n    , u\n\nWHERE 1=1\n    AND a = 1\n    AND b = 'x'\n")),
        ('SELECT a FROM t HAVING a>1 AND a<3 ORDER BY a;',
         'SELECT\n    a\nFROM t\n\nHAVING 1=1\n    AND a > 1\n    AND a < 3\n\nORDER BY a\n;\n'),
        ('select a from t group by a,b order by a desc,b;',
         'SELECT\n    a\nFROM t\n\nGROUP BY\n    a\n    , b\n\nORDER BY\n    a DESC\n    , b\n;\n'),
        ("SELECT COALESCE(a,b) AS x FROM t GROUP BY COALESCE(a,b),'a,b' ORDER BY x DESC NULLS LAST,a;",
         "SELECT\n    COALESCE(a,b) AS x\nFROM t\n\nGROUP BY\n    COALESCE(a,b)\n    , 'a,b'\n\nORDER BY\n    x DESC NULLS LAST\n    , a\n;\n"),
    ]

    def test_exact_first_output(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_idempotence_independent_of_expected(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_token_and_comment_preservation_independently(self):
        from formatter import validate_sql_unchanged, sql_tokens
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(sql_tokens(source)[1], sql_tokens(first)[1])

    def test_whitespace_variants_have_identical_first_result(self):
        variants = [
            'SELECT a,b FROM t GROUP BY a,b ORDER BY a DESC,b;',
            'SELECT\n a,\n b\nFROM t\nGROUP BY a,b\nORDER BY a DESC,b;',
            '\t SELECT  a , b\n   FROM\t t\n\n\t GROUP\tBY\n a ,\n\tb\n  ORDER  BY a DESC , b;',
            self.GROUP_ORDER,
        ]
        for source in variants:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, self.GROUP_ORDER)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_both_original_group_order_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        for cases in (GOLDEN, V12):
            source, expected = cases['group_and_order_multiple']
            self.assertEqual(format_sql(source, diagnostics=[]), expected)
            self.assertEqual(format_sql(expected, diagnostics=[]), expected)

    def test_multiple_from_with_each_list_clause(self):
        for clause in ('GROUP BY a,b', 'ORDER BY a,b', 'GROUP BY a,b ORDER BY a,b'):
            source = 'SELECT a,b FROM users a,payments b ' + clause + ';'
            with self.subTest(clause=clause):
                first = format_sql(source, diagnostics=[])
                self.assertIn('FROM users a\n    , payments b\n\n', first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_having_predicate_bytes_are_preserved_with_b44_layout(self):
        from sqlfluff.core import Linter
        from formatter import walk
        source = "SELECT a FROM t WHERE a=1 AND b=2 GROUP BY a HAVING SUM(a+1)>2 AND MAX(b)='  x' ORDER BY a;"
        first = format_sql(source, diagnostics=[])
        def having(sql):
            return next(s.raw for s in walk(Linter(dialect='teradata').parse_string(sql).tree)
                        if s.is_type('having_clause'))
        self.assertEqual(having(first), "HAVING 1=1\n    AND SUM(a+1) > 2\n    AND MAX(b) = '  x'")
        from formatter import validate_sql_unchanged
        validate_sql_unchanged(source, first)
        self.assertIn('WHERE 1=1', first)
        self.assertEqual(first.count('HAVING 1=1'), 1)
        self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_window_order_and_other_future_contexts_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in (
                'SELECT ROW_NUMBER() OVER (ORDER BY a,b) AS n FROM t ORDER BY n;',
                'SELECT a FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY a)=1;',
                'SELECT a FROM t JOIN u ON t.a=u.a GROUP BY a;',
                'WITH c AS (SELECT a FROM t) SELECT a FROM c ORDER BY a;',
                'SELECT a FROM t UNION ALL SELECT a FROM u;',
                'SELECT a FROM t GROUP BY a,\n-- b\nb;'):
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                self.assertEqual(nested_query_gap_edits(source, tree, include_simple=True), ([], set()))

    def test_comments_literals_and_existing_where_with_order(self):
        from formatter import validate_sql_unchanged
        for source in (
                "SELECT a, -- keep\n b FROM t WHERE a='a  b' AND b=2 GROUP BY a,b ORDER BY a,b;",
                "SELECT a FROM t WHERE a=1 AND b='x' ORDER BY a;",
                'SELECT a FROM t WHERE 1=1 AND a=1 AND b=2 GROUP BY a ORDER BY a;',
                'SELECT a FROM t WHERE a BETWEEN 1 AND 2 GROUP BY a ORDER BY a;'):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)
                if '-- keep' in source:
                    self.assertIn('a -- keep\n    , b', first)

    def test_new_list_edits_remain_one_atomic_group(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits
        source = self.CASES[0][0]
        edits, owners = nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree,
                                              include_simple=True)
        self.assertEqual(owners, {0})
        self.assertEqual(len({e.group_id for e in edits}), 1)
        edit = next(e for e in edits if e.start < e.end)
        accepted, warnings = plan_edits(source, edits, protected=[(edit.start, edit.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))

if __name__ == "__main__":
    unittest.main()
