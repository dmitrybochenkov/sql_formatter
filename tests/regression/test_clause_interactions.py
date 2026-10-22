"""Regression coverage: clause interactions. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B45IntegrationTests(unittest.TestCase):
    BASE = 'SELECT\n    a\nFROM t\n\n'
    CASES = {
        'direct_and_between_brackets': (
            'SELECT a FROM t WHERE a=1 AND b BETWEEN 2 AND 3 AND (c=4 OR d=5);',
            BASE + 'WHERE 1=1\n    AND a = 1\n    AND b BETWEEN 2 AND 3\n    AND (c = 4 OR d = 5)\n;\n'),
        'top_level_or': (
            'SELECT a FROM t WHERE a=1 AND b=2 OR c=3;',
            BASE + 'WHERE a = 1 AND b = 2 OR c = 3\n;\n'),
        'bracketed_only': (
            'SELECT a FROM t WHERE (a=1 AND b=2);',
            BASE + 'WHERE (a = 1 AND b = 2)\n;\n'),
        'between_only': (
            'SELECT a FROM t WHERE a BETWEEN 1 AND 2;',
            BASE + 'WHERE a BETWEEN 1 AND 2\n;\n'),
        'in_nested_where': (
            'SELECT a FROM t WHERE a IN (SELECT x FROM u WHERE p=1 AND q=2);',
            BASE + 'WHERE a IN (\n    SELECT\n        x\n    FROM u\n\n    WHERE 1=1\n        AND p = 1\n        AND q = 2\n)\n;\n'),
        'exists_outer_and': (
            'SELECT a FROM t WHERE a=1 AND EXISTS (SELECT x FROM u WHERE x=t.a AND p=2);',
            BASE + 'WHERE 1=1\n    AND a = 1\n    AND EXISTS (\n        SELECT\n            x\n        FROM u\n\n        WHERE 1=1\n            AND x = t.a\n            AND p = 2\n    )\n;\n'),
        'join_all_clauses': (
            'SELECT t.a FROM t JOIN u ON t.a=u.a AND u.b=2 WHERE t.a=1 AND u.c=3 GROUP BY t.a HAVING COUNT(*)>1 AND SUM(u.b)>2 ORDER BY t.a;',
            'SELECT\n    t.a\nFROM t\n\nJOIN u\nON t.a = u.a\n    AND u.b = 2\n\nWHERE 1=1\n    AND t.a = 1\n    AND u.c = 3\n\nGROUP BY t.a\n\nHAVING 1=1\n    AND COUNT(*) > 1\n    AND SUM(u.b) > 2\n\nORDER BY t.a\n;\n'),
        'ordinary_join_nested_where': (
            'SELECT t.a FROM t JOIN u ON t.a=u.a WHERE t.a IN (SELECT x FROM v WHERE p=1 AND q=2);',
            'SELECT\n    t.a\nFROM t\n\nJOIN u\nON t.a = u.a\n\nWHERE t.a IN (\n    SELECT\n        x\n    FROM v\n\n    WHERE 1=1\n        AND p = 1\n        AND q = 2\n)\n;\n'),
        'comment_before_where': (
            'SELECT id -- final field\nFROM users\n-- active only\nWHERE active=1;',
            'SELECT\n    id -- final field\nFROM users\n\n-- active only\nWHERE active = 1\n;\n'),
        'comments_between_and_after': (
            'SELECT a FROM t WHERE a=1 -- first\nAND b=2\n-- third\nAND c=3;',
            BASE + 'WHERE 1=1\n    AND a = 1 -- first\n    AND b = 2\n    -- third\n    AND c = 3\n;\n'),
        'nested_select_comments': (
            'SELECT a FROM t WHERE a=1 AND a IN (\n-- inner\nSELECT x FROM u WHERE p=2 AND q=3\n-- close\n);',
            BASE + 'WHERE 1=1\n    AND a = 1\n    AND a IN (\n        -- inner\n        SELECT\n            x\n        FROM u\n\n        WHERE 1=1\n            AND p = 2\n            AND q = 3\n    -- close\n    )\n;\n'),
        'literal_sql_and_commas': (
            "SELECT a FROM t WHERE b='SELECT, WHERE AND 1=1' AND c='it''s, OK';",
            BASE + "WHERE 1=1\n    AND b = 'SELECT, WHERE AND 1=1'\n    AND c = 'it''s, OK'\n;\n"),
        'multiline_equivalent': (
            '  SELECT a\n    FROM t\n WHERE a=1\n AND b BETWEEN 2 AND 3\n AND (c=4 OR d=5);',
            BASE + 'WHERE 1=1\n    AND a = 1\n    AND b BETWEEN 2 AND 3\n    AND (c = 4 OR d = 5)\n;\n'),
        'detached_comment': (
            'SELECT a FROM t WHERE a=1\n-- detached\n\nAND b=2;',
            BASE + 'WHERE a = 1\n-- detached\n\nAND b = 2\n;\n'),
    }

    def test_derived_join_boundaries_are_owned_atomically(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('SELECT t.a FROM t JOIN (SELECT a FROM u) s ON t.a=s.a;',
                       'SELECT t.a FROM (SELECT a FROM t) t JOIN u ON t.a=u.a;'):
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                edits, owners = nested_query_gap_edits(source, tree, include_simple=True,
                    include_joins=True, include_comment_lists=True, include_having=True)
                self.assertEqual(owners, {0})
                self.assertTrue(edits)
                self.assertEqual(len({e.group_id for e in edits}), 1)

    def test_exact_matrix(self):
        for name, (source, expected) in self.CASES.items():
            with self.subTest(name=name):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_matrix_invariants(self):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        def protected(sql):
            return [(p.kind, sql[p.start:p.end]) for p in protected_spans(sql)]
        for name, (source, _) in self.CASES.items():
            with self.subTest(name=name):
                first_diagnostics, second_diagnostics = [], []
                first = format_sql(source, diagnostics=first_diagnostics)
                second = format_sql(first, diagnostics=second_diagnostics)
                self.assertEqual(second, first)
                validate_sql_unchanged(source, first)
                self.assertEqual(protected(source), protected(first))
                for diagnostics in (first_diagnostics, second_diagnostics):
                    self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002') for d in diagnostics))
                    if name == 'detached_comment':
                        self.assertTrue(any(d.code == 'SQLFMT-C001' for d in diagnostics))
                    elif name == 'top_level_or':
                        self.assertTrue(any(d.code == 'SQLFMT-W001' for d in diagnostics))
                    else:
                        self.assertEqual(diagnostics, [])

    def test_matrix_edits_are_atomic(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits, Edit, apply_edits
        from formatter_modules.formatter_protection import protected_spans
        for name, (source, _) in self.CASES.items():
            with self.subTest(name=name):
                tree = Linter(dialect='teradata').parse_string(source).tree
                edits, owners = nested_query_gap_edits(source, tree, include_simple=True,
                    include_joins=True, include_comment_lists=True, include_having=True)
                self.assertEqual(owners, {0})
                self.assertEqual(len({e.group_id for e in edits}), 1)
                spans = [(p.start, p.end) for p in protected_spans(source)]
                accepted, warnings = plan_edits(source, edits, protected=spans)
                self.assertEqual(warnings, [])
                self.assertEqual(len(accepted), len(edits))
                reverse, warnings = plan_edits(source, list(reversed(edits)), protected=spans)
                self.assertEqual(apply_edits(source, accepted), apply_edits(source, reverse))
                edit = next((e for e in edits if e.start < e.end), edits[0])
                accepted, warnings = plan_edits(source, edits, protected=spans + [(edit.start - 1 if edit.start == edit.end else edit.start,
                                                                          max(edit.end, edit.start + 1))])
                self.assertEqual(accepted, [])
                self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))
                accepted, warnings = plan_edits(source, [Edit(edit.start, edit.start, ' ', 'TEST')] + edits)
                self.assertFalse(any(e.group_id for e in accepted))
                self.assertTrue(any(d.code == 'SQLFMT-E001' for d in warnings))

if __name__ == "__main__":
    unittest.main()
