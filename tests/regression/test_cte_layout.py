"""Regression coverage: cte layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B51CTETests(unittest.TestCase):
    def check_cte(self, source, expected):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        d1, d2 = [], []
        first = format_sql(source, diagnostics=d1)
        self.assertEqual(first, expected)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        def protected(sql):
            return [(p.kind, sql[p.start:p.end]) for p in protected_spans(sql)]
        self.assertEqual(protected(source), protected(first))
        self.assertEqual(d1, [])
        self.assertEqual(d2, [])

    def test_three_old_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        from tests.fixtures.edge_cases import GOLDEN as EDGE
        for cases, key in ((GOLDEN, 'ctes_separated'), (V12, 'ctes_separated'),
                           (EDGE, 'nested_cte_select_from_no_blank')):
            with self.subTest(key=key):
                self.check_cte(*cases[key])

    def test_where_scopes_are_independent(self):
        self.check_cte('WITH c AS (SELECT a FROM t WHERE p=1 AND q=2) SELECT a FROM c WHERE a=3;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n\n    WHERE 1=1\n        AND p = 1\n        AND q = 2\n)\n\nSELECT\n    a\nFROM c\n\nWHERE a = 3\n;\n')
        self.check_cte('WITH c AS (SELECT a FROM t WHERE p=1) SELECT a FROM c WHERE a=2 AND b=3;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n\n    WHERE p = 1\n)\n\nSELECT\n    a\nFROM c\n\nWHERE 1=1\n    AND a = 2\n    AND b = 3\n;\n')

    def test_join_group_having_order(self):
        self.check_cte('WITH c AS (SELECT t.a FROM t JOIN u ON t.a=u.a GROUP BY t.a HAVING COUNT(*)>1 AND SUM(u.b)>2 ORDER BY t.a) SELECT a FROM c;',
            'WITH c AS (\n    SELECT\n        t.a\n    FROM t\n\n    JOIN u\n    ON t.a = u.a\n\n    GROUP BY t.a\n\n    HAVING 1=1\n        AND COUNT(*) > 1\n        AND SUM(u.b) > 2\n\n    ORDER BY t.a\n)\n\nSELECT\n    a\nFROM c\n;\n')

    def test_nested_select_inside_cte(self):
        self.check_cte('WITH c AS (SELECT a FROM t WHERE a IN (SELECT x FROM u WHERE p=1 AND q=2) AND b=3) SELECT a FROM c;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n\n    WHERE 1=1\n        AND a IN (\n            SELECT\n                x\n            FROM u\n\n            WHERE 1=1\n                AND p = 1\n                AND q = 2\n        )\n        AND b = 3\n)\n\nSELECT\n    a\nFROM c\n;\n')

    def test_leading_and_body_comment_chain(self):
        self.check_cte('-- start\nWITH c AS (\n-- body\nSELECT a FROM t),\n-- next\n/* keep\n bytes */\nd AS (SELECT a FROM c) SELECT a FROM d;',
            '-- start\nWITH c AS (\n    -- body\n    SELECT\n        a\n    FROM t\n)\n\n-- next\n/* keep\n bytes */\n, d AS (\n    SELECT\n        a\n    FROM c\n)\n\nSELECT\n    a\nFROM d\n;\n')

    def test_trailing_comment_stays_with_previous_cte(self):
        self.check_cte('WITH c AS (SELECT a FROM t), -- previous\nd AS (SELECT a FROM c) SELECT a FROM d;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n) -- previous\n\n, d AS (\n    SELECT\n        a\n    FROM c\n)\n\nSELECT\n    a\nFROM d\n;\n')

    def test_keyword_case_columns_and_literals(self):
        self.check_cte("with c(a,b) as(select x,'WITH, SELECT WHERE AND' from t) select a from c;",
            "WITH c(a,b) AS (\n    SELECT\n        x\n        , 'WITH, SELECT WHERE AND'\n    FROM t\n)\n\nSELECT\n    a\nFROM c\n;\n")

    def test_scalar_select_and_multiline_inputs(self):
        expected = 'WITH c AS (\n    SELECT\n        1 AS a\n)\n\nSELECT\n    a\nFROM c\n;\n'
        for source in ('WITH c AS (SELECT 1 AS a) SELECT a FROM c;',
                       '  WITH c\n AS (\n    SELECT 1 AS a\n )\n  SELECT a\n FROM c;'):
            self.check_cte(source, expected)

    def test_ambiguous_separator_is_not_guessed(self):
        from formatter import validate_sql_unchanged
        source = 'WITH c AS (SELECT a FROM t),\n-- detached\n\nd AS (SELECT a FROM c) SELECT a FROM d;'
        d1, d2 = [], []
        first = format_sql(source, diagnostics=d1)
        self.assertIn('),\n-- detached\n\nd AS (', first)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        for diagnostics in (d1, d2):
            self.assertTrue(any(d.code == 'SQLFMT-C001' for d in diagnostics))
            self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002') for d in diagnostics))

    def test_cte_edits_atomic_with_protection_conflict_and_order(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits, apply_edits, Edit
        from formatter_modules.formatter_protection import protected_spans
        source = "with c as(select 'x,y' AS x from t),\n-- next\nd as(select x from c) select x from d;"
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits, owners = nested_query_gap_edits(source, tree, include_simple=True, include_cte=True)
        self.assertEqual(owners, {0})
        self.assertEqual(len({e.group_id for e in edits}), 1)
        spans = [(p.start, p.end) for p in protected_spans(source)]
        accepted, warnings = plan_edits(source, edits, protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(len(accepted), len(edits))
        reverse, warnings = plan_edits(source, list(reversed(edits)), protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(apply_edits(source, accepted), apply_edits(source, reverse))
        comma_edit = next(e for e in edits if ',' in source[e.start:e.end])
        accepted, warnings = plan_edits(source, edits, protected=spans + [(comma_edit.start, comma_edit.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))
        accepted, warnings = plan_edits(source, [Edit(comma_edit.start, comma_edit.start, ' ', 'TEST')] + edits)
        group_edits = [e for e in accepted if e.group_id]
        self.assertIn(len(group_edits), (0, len(edits)))
        self.assertFalse(group_edits and any(e.rule_id == 'TEST' for e in accepted))
        self.assertTrue(any(d.code == 'SQLFMT-E001' for d in warnings))

    def test_cte_derived_join_supported_other_feature_gates_preserved(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('WITH c AS (SELECT a FROM t UNION ALL SELECT a FROM u) SELECT a FROM c;',
                       'WITH c AS (SELECT ROW_NUMBER() OVER (ORDER BY a) AS n FROM t) SELECT n FROM c;',
                       'WITH c AS (SELECT a FROM t QUALIFY a=1) SELECT a FROM c;',
                       'WITH c AS (SELECT t.a FROM t JOIN (SELECT a FROM u) s ON t.a=s.a) SELECT a FROM c;'):
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                result = nested_query_gap_edits(source, tree, include_simple=True,
                    include_joins=True, include_comment_lists=True, include_having=True, include_cte=True)
                if 'JOIN (' in source:
                    self.assertEqual(result[1], {0})
                    self.assertTrue(result[0])
                else:
                    self.assertEqual(result, ([], set()))

if __name__ == "__main__":
    unittest.main()
