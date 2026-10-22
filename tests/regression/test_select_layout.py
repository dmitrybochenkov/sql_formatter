"""Regression coverage: select layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B31SimpleQueryTests(unittest.TestCase):
    CASES = [
        ('SELECT id, name FROM users WHERE active=1;',
         'SELECT\n    id\n    , name\nFROM users\n\nWHERE active = 1\n;\n'),
        ('SELECT id FROM users;', 'SELECT\n    id\nFROM users\n;\n'),
        ('SELECT u.id AS user_id,u.name display_name,u.age FROM users u;',
         'SELECT\n    u.id AS user_id\n    , u.name display_name\n    , u.age\nFROM users u\n;\n'),
        ('SELECT DISTINCT id,name FROM users;',
         'SELECT DISTINCT\n    id\n    , name\nFROM users\n;\n'),
        ('SELECT *,u.id FROM users u WHERE u.id>=10;',
         'SELECT\n    *\n    , u.id\nFROM users u\n\nWHERE u.id >= 10\n;\n'),
        ("SELECT 'a  b' AS txt,id FROM users WHERE name='it''s  fine';",
         "SELECT\n    'a  b' AS txt\n    , id\nFROM users\n\nWHERE name = 'it''s  fine'\n;\n"),
        ('SELECT id FROM users WHERE active=1 AND age>18;',
         'SELECT\n    id\nFROM users\n\nWHERE 1=1\n    AND active = 1\n    AND age > 18\n;\n'),
        ('SELECT id FROM users WHERE age BETWEEN 1 AND 5;',
         'SELECT\n    id\nFROM users\n\nWHERE age BETWEEN 1 AND 5\n;\n'),
    ]

    def test_exact_simple_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_simple_idempotence_independently(self):
        # Do not hide second-pass failures behind exact-output assertions.
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_simple_token_preservation_independently(self):
        from formatter import validate_sql_unchanged, sql_tokens
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(sql_tokens(source)[1], sql_tokens(first)[1])
                self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002')
                                     for d in self._diagnostics(source)))

    @staticmethod
    def _diagnostics(source):
        diagnostics = []
        format_sql(source, diagnostics=diagnostics)
        return diagnostics

    def test_whitespace_variants_have_one_result(self):
        expected = self.CASES[0][1]
        for source in (
            'SELECT id,name FROM users WHERE active=1;',
            '  SELECT  id ,  name\n\n  FROM   users\n WHERE active = 1 ;',
            '\tSELECT\n id\n, name\n\nFROM\n users\n\n\nWHERE active=1\n;',
        ):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, expected)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_comparison_operators_remain_whole(self):
        from formatter import sql_tokens
        for operator in ('=', '<', '>', '<=', '>=', '<>', '!='):
            source = f'SELECT id FROM users WHERE age{operator}18;'
            with self.subTest(operator=operator):
                first = format_sql(source, diagnostics=[])
                self.assertIn(f'WHERE age {operator} 18\n;', first)
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_comment_attachment_and_literal_bytes(self):
        from formatter import sql_tokens
        cases = [
            ("SELECT id, -- identifier\n name FROM users WHERE name='a  b';",
             'id -- identifier\n    , name\nFROM users'),
            ('SELECT\n-- identifier\nid FROM users;',
             'SELECT\n    -- identifier\n    id\nFROM users'),
            ('SELECT id -- final field\nFROM users\n-- active only\nWHERE active=1;',
             'id -- final field\nFROM users\n\n-- active only\nWHERE active = 1'),
            ('SELECT id FROM users WHERE active/* keep */=1;',
             'active/* keep */= 1'),
        ]
        for source, fragment in cases:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertIn(fragment, first)
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_new_pass_skips_out_of_scope_constructs(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import simple_query_gap_edits
        cases = [
            'WITH c AS (SELECT id FROM t) SELECT id FROM c;',
            'SELECT id FROM t WHERE id IN (SELECT id FROM u);',
            'SELECT t.id FROM t JOIN u ON t.id=u.id;',
            'SELECT id FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY id)=1;',
            'SELECT ROW_NUMBER() OVER (ORDER BY id) FROM t;',
            'SELECT id FROM t GROUP BY id;',
            'SELECT id FROM t UNION ALL SELECT id FROM u;',
            'SELECT a.id FROM a,b;',
        ]
        for source in cases:
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                self.assertEqual(simple_query_gap_edits(source, tree), [])

    def test_boundary_pass_edits_only_whitespace(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import simple_query_gap_edits
        source = '  SELECT id, name FROM users WHERE active>=1;'
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits = simple_query_gap_edits(source, tree)
        self.assertTrue(edits)
        for edit in edits:
            self.assertFalse(source[edit.start:edit.end].strip())
            self.assertFalse(edit.replacement.strip())
            self.assertIsNotNone(edit.group_id)

class B32NestedQueryTests(unittest.TestCase):
    CASES = [
        ('SELECT id FROM t WHERE id IN (SELECT x,y FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE id IN (\n    SELECT\n        x\n        , y\n    FROM u\n)\n;\n'),
        ('SELECT q.id FROM (SELECT id,name FROM u WHERE active=1) q;',
         'SELECT\n    q.id\nFROM (\n    SELECT\n        id\n        , name\n    FROM u\n\n    WHERE active = 1\n) q\n;\n'),
        ('SELECT id FROM t WHERE a=1 AND id IN (SELECT x,y FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n    AND id IN (\n'
         '        SELECT\n            x\n            , y\n        FROM u\n    )\n;\n'),
        ("SELECT id FROM t WHERE note='SELECT FROM WHERE' AND id IN (SELECT 'SELECT FROM WHERE' AS x FROM u);",
         "SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND note = 'SELECT FROM WHERE'\n"
         "    AND id IN (\n        SELECT\n            'SELECT FROM WHERE' AS x\n        FROM u\n    )\n;\n"),
        ('SELECT id FROM t WHERE id IN ( -- open\nSELECT x FROM u -- close\n);',
         'SELECT\n    id\nFROM t\n\nWHERE id IN ( -- open\n    SELECT\n        x\n    FROM u -- close\n)\n;\n'),
        ('SELECT q.x FROM (\n-- inner\nSELECT x,y FROM u\n) q;',
         'SELECT\n    q.x\nFROM (\n    -- inner\n    SELECT\n        x\n        , y\n    FROM u\n) q\n;\n'),
        ('SELECT (SELECT x FROM u WHERE x=1) AS value,id FROM t;',
         'SELECT\n    (\n        SELECT\n            x\n        FROM u\n\n        WHERE x = 1\n    ) AS value\n    , id\nFROM t\n;\n'),
        ('SELECT q.x FROM (SELECT p.x FROM (SELECT x,y FROM v) p) q;',
         'SELECT\n    q.x\nFROM (\n    SELECT\n        p.x\n    FROM (\n        SELECT\n            x\n            , y\n        FROM v\n    ) p\n) q\n;\n'),
        ('SELECT id FROM t WHERE a BETWEEN 1 AND 3 AND id IN (SELECT x FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a BETWEEN 1 AND 3\n    AND id IN (\n        SELECT\n            x\n        FROM u\n    )\n;\n'),
        ('SELECT id FROM t WHERE a=1 OR id IN (SELECT x FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE a = 1 OR id IN (\n    SELECT\n        x\n    FROM u\n)\n;\n'),
    ]

    def test_exact_nested_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_nested_idempotence_independently(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_nested_tokens_literals_comments_independently(self):
        from formatter import sql_tokens, validate_sql_unchanged, remove_formatter_where_prefix
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                before, comments = sql_tokens(source)
                after, actual_comments = sql_tokens(first)
                self.assertEqual(comments, actual_comments)
                self.assertEqual(remove_formatter_where_prefix(before), remove_formatter_where_prefix(after))
                self.assertEqual([t for t in before if 'literal' in t[0] and t[0] != 'numeric_literal'],
                                 [t for t in after if 'literal' in t[0] and t[0] != 'numeric_literal'])

    def test_indentation_ignores_original_columns(self):
        expected = self.CASES[2][1]
        for source in (
                '   SELECT id FROM t WHERE a=1 AND id IN (\n SELECT x,y FROM u\n);',
                '\tSELECT id\n  FROM t\n WHERE a = 1 AND id IN (\n\t\tSELECT x, y\n FROM u\n        );',
                expected):
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_where_prefix_is_exact_and_validator_stays_strict(self):
        from formatter import validate_sql_unchanged, sql_tokens
        source, expected = self.CASES[2]
        self.assertEqual(len(sql_tokens(expected)[0]) - len(sql_tokens(source)[0]), 4)
        validate_sql_unchanged(source, expected)
        for altered in (expected.replace('WHERE 1=1', 'WHERE 2=2'),
                        expected.replace('AND a = 1', 'AND a = 2'),
                        expected.replace('AND id IN', 'OR id IN'),
                        expected.replace('FROM u', 'FROM v')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                validate_sql_unchanged(source, altered)
        for source, expected in (self.CASES[3], self.CASES[4]):
            altered = expected.replace("'SELECT FROM WHERE'", "'changed'").replace('-- open', '-- changed')
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_sql_unchanged(source, altered)

    def test_existing_prefix_siblings_and_multiline_literals_are_stable(self):
        from formatter import validate_sql_unchanged
        cases = [
            'SELECT id FROM t WHERE 1 = 1 AND a=1 AND id IN (SELECT x FROM u);',
            'SELECT id FROM t WHERE id IN (SELECT x FROM u) AND id IN (SELECT y FROM v);',
            "SELECT id FROM t WHERE a=1 AND id IN (SELECT 'a\n\nb' AS x FROM u);",
            'SELECT q.x FROM (/* inner */ SELECT x FROM u /* tail */) q;',
            '\nSELECT id FROM t WHERE id IN (SELECT x FROM u);\nSELECT q.x FROM (SELECT x FROM u WHERE x>=2) q;',
        ]
        for source in cases:
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                self.assertEqual(first, format_sql(first, diagnostics=[]))
                validate_sql_unchanged(source, first)
                self.assertEqual(warnings, [])
        self.assertEqual(format_sql(cases[0], diagnostics=[]).count('WHERE 1=1'), 1)
        self.assertIn("'a\n\nb'", format_sql(cases[2], diagnostics=[]))

    def test_no_parent_edit_covers_child_and_no_e001_is_suppressed(self):
        from unittest.mock import patch
        from sqlfluff.core import Linter
        from formatter import walk
        from formatter_modules.formatter_edits import plan_edits
        source = self.CASES[2][0]
        warnings = []
        with patch('formatter.plan_edits', wraps=plan_edits) as planner:
            format_sql(source, diagnostics=warnings)
        self.assertFalse(any(d.code == 'SQLFMT-E001' for d in warnings))
        for call in planner.call_args_list:
            snapshot, candidates = call.args[:2]
            tree = Linter(dialect='teradata').parse_string(snapshot).tree
            children = [n.pos_marker.source_slice for n in walk(tree) if n.is_type('select_statement')][1:]
            for edit in candidates:
                self.assertFalse(edit.rule_id == 'LEGACY-AST' and edit.owner.startswith('where_clause'))
                for child in children:
                    self.assertFalse(edit.start < child.start and edit.end > child.start)
                    self.assertFalse(edit.start < child.stop and edit.end > child.stop)

    def test_nested_prepass_group_rejects_protection_or_conflict_atomically(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import Edit, plan_edits
        source = self.CASES[2][0]
        edits, _ = nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree)
        self.assertGreater(len(edits), 2)
        self.assertEqual(len({e.group_id for e in edits}), 1)
        target = next(e for e in edits if e.start < e.end)
        accepted, warnings = plan_edits(source, edits, protected=[(target.start, target.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(w.code == 'SQLFMT-E002' for w in warnings))
        conflict = Edit(target.start, target.start, ' ', 'TEST-CONFLICT')
        accepted, warnings = plan_edits(source, [conflict] + edits, protected=[])
        self.assertEqual(accepted, [conflict])
        self.assertTrue(any(w.code == 'SQLFMT-E001' for w in warnings))

    def test_out_of_scope_queries_are_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in (
                'WITH c AS (SELECT id FROM u) SELECT id FROM c;',
                'SELECT t.id FROM t JOIN (SELECT id FROM u) q ON q.id=t.id;',
                'SELECT id FROM t WHERE id IN (SELECT id FROM u) QUALIFY id=1;',
                'SELECT ROW_NUMBER() OVER (ORDER BY id) FROM (SELECT id FROM u) q;',
                'SELECT id FROM t UNION SELECT id FROM (SELECT id FROM u) q;',
                'SELECT id FROM t WHERE id IN (SELECT id FROM u GROUP BY id);'):
            with self.subTest(source=source):
                self.assertEqual(nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree), ([], set()))

if __name__ == "__main__":
    unittest.main()
