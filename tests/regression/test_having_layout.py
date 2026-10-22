"""Regression coverage: having layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B44HavingTests(unittest.TestCase):
    PREFIX = 'SELECT\n    a\nFROM t\n\nGROUP BY a\n\n'

    def check_having(self, predicate, expected_predicate, header='HAVING'):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        source = 'SELECT a FROM t GROUP BY a ' + header + ' ' + predicate + ';'
        expected = self.PREFIX + header.upper() + ' ' + expected_predicate + '\n;\n'
        diagnostics = []
        actual = format_sql(source, diagnostics=diagnostics)
        self.assertEqual(actual, expected)
        self.assertEqual(diagnostics, [])
        second = []
        self.assertEqual(format_sql(actual, diagnostics=second), actual)
        self.assertEqual(second, [])
        validate_sql_unchanged(source, actual)
        def spans(sql):
            return [(p.kind, sql[p.start:p.end]) for p in protected_spans(sql)]
        self.assertEqual(spans(source), spans(actual))

    def test_single_and_multiple_conditions(self):
        self.check_having('COUNT(*)>1', 'COUNT(*) > 1')
        self.check_having('COUNT(*)>1 AND SUM(a)>2 AND MAX(b)<=9',
                          '1=1\n    AND COUNT(*) > 1\n    AND SUM(a) > 2\n    AND MAX(b) <= 9')

    def test_between_or_and_brackets(self):
        for source, expected in (
            ('SUM(a) BETWEEN 1 AND 2', 'SUM(a) BETWEEN 1 AND 2'),
            ('(SUM(a)>1 AND MAX(b)>2)', '(SUM(a) > 1 AND MAX(b) > 2)'),
            ('SUM(a)>1 AND MAX(b)>2 OR MIN(c)>3', 'SUM(a) > 1 AND MAX(b) > 2 OR MIN(c) > 3'),
            ('SUM(a) BETWEEN 1 AND 2 AND (MAX(b)>2 OR MIN(c)<3)',
             '1=1\n    AND SUM(a) BETWEEN 1 AND 2\n    AND (MAX(b) > 2 OR MIN(c) < 3)')):
            with self.subTest(source=source):
                self.check_having(source, expected)

    def test_case_literals_and_existing_prefix(self):
        self.check_having("MAX(b)='HAVING AND 1=1' and SUM(a+1)>2",
                          "1=1\n    AND MAX(b) = 'HAVING AND 1=1'\n    AND SUM(a+1) > 2", header='having')
        self.check_having('1=1 and COUNT(*)>1 AND SUM(a)>2',
                          '1=1\n    AND COUNT(*) > 1\n    AND SUM(a) > 2', header='HaViNg')

    def test_comments_and_header_comments(self):
        self.check_having("MAX(b)='OK' AND SUM(a)>1 -- left\nAND MIN(c)<9",
                          "1=1\n    AND MAX(b) = 'OK'\n    AND SUM(a) > 1 -- left\n    AND MIN(c) < 9")
        self.check_having('SUM(a)>1\n-- next\n/* keep\n bytes */\nAND MAX(b)>2',
                          '1=1\n    AND SUM(a) > 1\n    -- next\n    /* keep\n bytes */\n    AND MAX(b) > 2')
        self.check_having('-- header\nSUM(a)>1 AND MAX(b)>2',
                          '1=1 -- header\n    AND SUM(a) > 1\n    AND MAX(b) > 2')
        self.check_having('\n-- first\nSUM(a)>1 AND MAX(b)>2',
                          '1=1\n    -- first\n    AND SUM(a) > 1\n    AND MAX(b) > 2')

    def test_subquery_ands_do_not_trigger_outer_prefix(self):
        self.check_having('SUM(a)>(SELECT x FROM u WHERE p=1 AND q=2)',
                          'SUM(a) > (\n    SELECT\n        x\n    FROM u\n\n    WHERE 1=1\n        AND p = 1\n        AND q = 2\n)')
        self.check_having('SUM(a)>(SELECT x FROM u WHERE p=1) AND MAX(b)>2',
                          '1=1\n    AND SUM(a) > (\n        SELECT\n            x\n        FROM u\n\n        WHERE p = 1\n    )\n    AND MAX(b) > 2')
        self.check_having('SUM(a)>(SELECT MAX(x) FROM u HAVING COUNT(*)>1 AND SUM(y)>2)',
                          'SUM(a) > (\n    SELECT\n        MAX(x)\n    FROM u\n\n    HAVING 1=1\n        AND COUNT(*) > 1\n        AND SUM(y) > 2\n)')

    def test_whitespace_variants_and_both_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        for cases in (GOLDEN, V12):
            source, expected = cases['having_two_ands']
            for variant in (source, source.replace(' HAVING ', '\n        HAVING\n ').replace(' AND ', '\n AND ')):
                self.assertEqual(format_sql(variant, diagnostics=[]), expected)
            self.assertEqual(format_sql(expected, diagnostics=[]), expected)

    def test_having_edits_are_atomic(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits, Edit
        from formatter_modules.formatter_protection import protected_spans
        source = "SELECT a FROM t HAVING MAX(b)='OK' AND SUM(a)>1;"
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits, owners = nested_query_gap_edits(source, tree, include_simple=True, include_having=True)
        self.assertEqual(owners, {0})
        self.assertEqual(len({e.group_id for e in edits}), 1)
        spans = [(p.start, p.end) for p in protected_spans(source)]
        accepted, warnings = plan_edits(source, edits, protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(len(accepted), len(edits))
        edit = next(e for e in edits if '1=1' in e.replacement)
        accepted, warnings = plan_edits(source, edits, protected=spans + [(edit.start, edit.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))
        accepted, warnings = plan_edits(source, [Edit(edit.start, edit.start, ' ', 'TEST')] + edits)
        self.assertFalse(any(e.group_id for e in accepted))
        self.assertTrue(any(d.code == 'SQLFMT-E001' for d in warnings))

if __name__ == "__main__":
    unittest.main()
