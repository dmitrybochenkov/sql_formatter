"""Regression coverage: set operations. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B52SetOperationTests(unittest.TestCase):
    def check_set(self, source, expected):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        d1, d2 = [], []
        first = format_sql(source, diagnostics=d1)
        self.assertEqual(first, expected)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        self.assertEqual([(p.kind, source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind, first[p.start:p.end]) for p in protected_spans(first)])
        self.assertEqual(d1, [])
        self.assertEqual(d2, [])

    def test_three_old_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        from tests.fixtures.edge_cases import GOLDEN as EDGE
        for cases, key in ((GOLDEN, 'union_all'), (V12, 'union_all'), (EDGE, 'set_operator_blank_lines')):
            with self.subTest(key=key):
                self.check_set(*cases[key])

    def test_operators_preserve_case_and_multiline_input(self):
        for operator in ('UNION', 'union all', 'union DISTINCT', 'Intersect', 'INTERSECT ALL', 'except', 'except all'):
            expected = 'SELECT\n    a\nFROM t\n\n' + operator.upper() + '\n\nSELECT\n    b\nFROM u\n;\n'
            for source in (f'SELECT a FROM t {operator} SELECT b FROM u;',
                           f'   SELECT a\n FROM t\n {operator}\n  SELECT b\nFROM u;'):
                with self.subTest(source=source):
                    self.check_set(source, expected)

    def test_three_branches_and_precedence(self):
        self.check_set('SELECT a FROM t UNION SELECT b FROM u INTERSECT SELECT c FROM v;',
            'SELECT\n    a\nFROM t\n\nUNION\n\nSELECT\n    b\nFROM u\n\nINTERSECT\n\nSELECT\n    c\nFROM v\n;\n')

    def test_parenthesized_set(self):
        self.check_set('(SELECT a FROM t UNION SELECT b FROM u) INTERSECT SELECT c FROM v;',
            '(\n    SELECT\n        a\n    FROM t\n\n    UNION\n\n    SELECT\n        b\n    FROM u\n)\n\nINTERSECT\n\nSELECT\n    c\nFROM v\n;\n')

    def test_independent_where_scopes(self):
        self.check_set('SELECT a FROM t WHERE p=1 AND q=2 UNION ALL SELECT b FROM u WHERE r=3;',
            'SELECT\n    a\nFROM t\n\nWHERE 1=1\n    AND p = 1\n    AND q = 2\n\nUNION ALL\n\nSELECT\n    b\nFROM u\n\nWHERE r = 3\n;\n')

    def test_global_order_group_and_having(self):
        self.check_set('SELECT a FROM t GROUP BY a HAVING COUNT(*)>1 AND SUM(b)>2 UNION SELECT a FROM u GROUP BY a HAVING COUNT(*)>3 ORDER BY a DESC;',
            'SELECT\n    a\nFROM t\n\nGROUP BY a\n\nHAVING 1=1\n    AND COUNT(*) > 1\n    AND SUM(b) > 2\n\nUNION\n\nSELECT\n    a\nFROM u\n\nGROUP BY a\n\nHAVING COUNT(*) > 3\n\nORDER BY a DESC\n;\n')

    def test_cte_body_and_main_set(self):
        self.check_set('WITH c AS (SELECT a FROM t EXCEPT SELECT b FROM u) SELECT a FROM c UNION SELECT a FROM t;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n\n    EXCEPT\n\n    SELECT\n        b\n    FROM u\n)\n\nSELECT\n    a\nFROM c\n\nUNION\n\nSELECT\n    a\nFROM t\n;\n')

    def test_nested_set_in_where(self):
        self.check_set('SELECT a FROM t WHERE a IN (SELECT b FROM u UNION SELECT c FROM v);',
            'SELECT\n    a\nFROM t\n\nWHERE a IN (\n    SELECT\n        b\n    FROM u\n\n    UNION\n\n    SELECT\n        c\n    FROM v\n)\n;\n')

    def test_literals_are_opaque(self):
        self.check_set("SELECT 'UNION, SELECT' AS a FROM t UNION ALL SELECT 'EXCEPT  x' AS a FROM u;",
            "SELECT\n    'UNION, SELECT' AS a\nFROM t\n\nUNION ALL\n\nSELECT\n    'EXCEPT  x' AS a\nFROM u\n;\n")

    def test_comments_around_operator(self):
        self.check_set('SELECT a FROM t -- left\nUNION ALL -- operator\nSELECT b FROM u;',
            'SELECT\n    a\nFROM t -- left\n\nUNION ALL -- operator\n\nSELECT\n    b\nFROM u\n;\n')
        self.check_set('SELECT a FROM t\n-- before\nUNION\n/* after\n keep */\nSELECT b FROM u;',
            'SELECT\n    a\nFROM t\n\n-- before\nUNION\n\n/* after\n keep */\nSELECT\n    b\nFROM u\n;\n')

    def test_ambiguous_comment(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT a FROM t\n-- detached\n\nUNION SELECT b FROM u;'
        d1, d2 = [], []
        first = format_sql(source, diagnostics=d1)
        self.assertIn('FROM t\n-- detached\n\nUNION', first)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        self.assertTrue(any(d.code == 'SQLFMT-C001' for d in d1))
        self.assertTrue(any(d.code == 'SQLFMT-C001' for d in d2))

    def test_atomic_protection_and_conflicts(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import Edit, plan_edits, apply_edits
        source = 'SELECT a FROM t UNION ALL SELECT b FROM u;'
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits, handled = nested_query_gap_edits(source, tree, include_simple=True, include_sets=True)
        self.assertEqual(handled, {0})
        self.assertTrue(edits)
        self.assertEqual(len({e.group_id for e in edits}), 1)
        e = edits[0]
        accepted, diagnostics = plan_edits(source, edits, protected=[(e.start - 1, e.end + 1)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in diagnostics))
        accepted, diagnostics = plan_edits(source, edits + [Edit(e.start, e.start, ' ', 'conflict')])
        members = [x for x in accepted if x.group_id == e.group_id]
        self.assertIn(len(members), (0, len(edits)))
        self.assertTrue(any(d.code == 'SQLFMT-E001' for d in diagnostics))
        forward, _ = plan_edits(source, edits)
        reverse, _ = plan_edits(source, list(reversed(edits)))
        self.assertEqual(apply_edits(source, forward), apply_edits(source, reverse))

    def test_validator_rejects_changes_between_branches(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT a FROM t WHERE p=1 AND q=2 UNION ALL SELECT b FROM u WHERE r=3;'
        valid = format_sql(source)
        for invalid in (valid.replace('UNION ALL', 'UNION'), valid.replace('UNION ALL', 'union all'),
                        valid.replace('WHERE r = 3', 'WHERE 1=1 AND r = 3'),
                        valid.replace('q = 2', 'q = 4'), valid.replace('FROM u', 'FROM v')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_sql_unchanged(source, invalid)

    def test_nested_parenthesized_set_is_rendered_once(self):
        self.check_set('SELECT a FROM t WHERE a IN ((SELECT b FROM u UNION SELECT c FROM v) INTERSECT SELECT d FROM w);',
            'SELECT\n    a\nFROM t\n\nWHERE a IN (\n    (\n        SELECT\n            b\n        FROM u\n\n        UNION\n\n        SELECT\n            c\n        FROM v\n    )\n\n    INTERSECT\n\n    SELECT\n        d\n    FROM w\n)\n;\n')

    def test_derived_set_and_branch_local_order(self):
        self.check_set('SELECT a FROM (SELECT a FROM t UNION ALL SELECT b FROM u) s;',
            'SELECT\n    a\nFROM (\n    SELECT\n        a\n    FROM t\n\n    UNION ALL\n\n    SELECT\n        b\n    FROM u\n) s\n;\n')
        self.check_set('(SELECT a FROM t ORDER BY a) UNION SELECT b FROM u;',
            '(\n    SELECT\n        a\n    FROM t\n\n    ORDER BY a\n)\n\nUNION\n\nSELECT\n    b\nFROM u\n;\n')

    def test_comment_inside_operator_and_global_order_list(self):
        self.check_set('SELECT a,b FROM t UNION /* keep */ ALL SELECT a,b FROM u ORDER BY a,\n-- key\nb DESC NULLS LAST;',
            'SELECT\n    a\n    , b\nFROM t\n\nUNION /* keep */ ALL\n\nSELECT\n    a\n    , b\nFROM u\n\nORDER BY\n    a\n    -- key\n    , b DESC NULLS LAST\n;\n')

    def test_both_branch_predicates_and_join(self):
        self.check_set('SELECT t.a FROM t JOIN v ON t.a=v.a WHERE p=1 AND q=2 UNION SELECT a FROM u WHERE r=3 AND s=4;',
            'SELECT\n    t.a\nFROM t\n\nJOIN v\nON t.a = v.a\n\nWHERE 1=1\n    AND p = 1\n    AND q = 2\n\nUNION\n\nSELECT\n    a\nFROM u\n\nWHERE 1=1\n    AND r = 3\n    AND s = 4\n;\n')

    def test_derived_join_supported_other_feature_gates_preserved(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('SELECT ROW_NUMBER() OVER (ORDER BY a) FROM t UNION SELECT b FROM u;',
                       'SELECT a FROM t QUALIFY a=1 UNION SELECT b FROM u;',
                       'SELECT a FROM t UNION SELECT a FROM u JOIN (SELECT a FROM v) s ON u.a=s.a;'):
            tree = Linter(dialect='teradata').parse_string(source).tree
            result = nested_query_gap_edits(source, tree, include_simple=True,
                include_joins=True, include_cte=True, include_sets=True)
            if 'JOIN (' in source:
                self.assertEqual(result[1], {0})
                self.assertTrue(result[0])
            else:
                self.assertEqual(result, ([], set()))

if __name__ == "__main__":
    unittest.main()
