"""Regression coverage: where layout. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B33BasicClauseTests(unittest.TestCase):
    CASES = [
        ('select id from users where active = 1;',
         'SELECT\n    id\nFROM users\n\nWHERE active = 1\n;\n'),
        ('SeLeCt Id from Users WhErE active=1;',
         'SELECT\n    id\nFROM users\n\nWHERE active = 1\n;\n'),
        ("select 'select FROM where' AS \"where\",MixedName from MixedTable where MixedName='WHERE';",
         'SELECT\n    \'select FROM where\' AS "where"\n    , mixedname\nFROM mixedtable\n\nWHERE mixedname = \'WHERE\'\n;\n'),
        ('SELECT a.id,b.name FROM a,b;',
         'SELECT\n    a.id\n    , b.name\nFROM a\n    , b\n;\n'),
        ('SELECT id,\n-- first\n-- second\nname FROM users;',
         'SELECT\n    id\n    -- first\n    -- second\n    , name\nFROM users\n;\n'),
        ("SELECT id FROM t WHERE active=1 AND (country='RU' OR country='BY');",
         "SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND active = 1\n    AND (country = 'RU' OR country = 'BY')\n;\n"),
        ('SELECT x+y AS total,-x AS neg,COUNT(*) AS n FROM t;',
         'SELECT\n    x + y AS total\n    , -x AS neg\n    , COUNT(*) AS n\nFROM t\n;\n'),
        ('select distinct Id from Users where a=1 and b=2;',
         'SELECT DISTINCT\n    id\nFROM users\n\nWHERE 1=1\n    AND a = 1\n    AND b = 2\n;\n'),
    ]

    def test_exact_basic_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_basic_idempotence_independently(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, format_sql(first, diagnostics=[]))

    def test_basic_validation_independently(self):
        from formatter import validate_sql_unchanged
        for source, _ in self.CASES:
            with self.subTest(source=source):
                validate_sql_unchanged(source, format_sql(source, diagnostics=[]))

    def test_all_nine_former_basic_failures_match_existing_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        from tests.fixtures.edge_cases import GOLDEN as EDGE
        for collection in (GOLDEN, V12):
            for name in ('from_multiple_tables', 'comment_above_element', 'where_or_inside_parentheses'):
                source, expected = collection[name]
                with self.subTest(name=name, collection=id(collection)):
                    actual = format_sql(source, diagnostics=[])
                    self.assertEqual(actual, expected)
                    self.assertEqual(format_sql(actual, diagnostics=[]), actual)
        source, expected = EDGE['consecutive_comment_lines']
        self.assertEqual(format_sql(source, diagnostics=[]), expected)
        self.assertIn('x + y', format_sql('SELECT x+y AS total FROM t;', diagnostics=[]))
        warnings = []
        source = 'SELECT id FROM t WHERE a=1 AND b=2 OR c=3;'
        actual = format_sql(source, diagnostics=warnings)
        self.assertTrue(any(d.code == 'SQLFMT-W001' for d in warnings))
        self.assertNotIn('WHERE 1=1', actual)
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)

    def test_nested_mixed_case_headers_and_prefix_are_stable(self):
        from formatter import validate_sql_unchanged
        source = 'select id from t where a=1 AND id IN (sElEcT x from u where b=2 AND c=3);'
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(warnings, [])
        self.assertEqual(first.count('WHERE 1=1'), 2)
        self.assertIn('        SELECT\n            x\n        FROM u', first)
        validate_sql_unchanged(source, first)
        self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_compact_header_boundaries_are_atomic_and_stable(self):
        from formatter import validate_sql_unchanged
        for source in ('select id from t where id IN (select x from u);',
                       'select q.x from(select x from u) q;'):
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                self.assertEqual(warnings, [])
                self.assertIn('\nFROM ', first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)
                validate_sql_unchanged(source, first)

    def test_operator_spacing_preserves_comments_literals_and_unary_signs(self):
        from formatter import sql_tokens, validate_sql_unchanged
        for source in (
                "SELECT x/* keep */+y, -x, x*-2, 'a+b' AS txt FROM t;",
                'SELECT x -- attached to x\n+y FROM t;',
                'SELECT x+y*z/2, x||y FROM t WHERE a+1>=2;',
                'SELECT id FROM t WHERE a -- attached to a\n=1;',
                'SELECT id FROM t WHERE a=/* keep */1;'):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                validate_sql_unchanged(source, first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_prefix_stays_single_and_between_is_not_an_and_chain(self):
        for source, count in (
                ('SELECT id FROM t WHERE a BETWEEN 1 AND 2;', 0),
                ('SELECT id FROM t WHERE a=1;', 0),
                ('SELECT id FROM t WHERE a BETWEEN 1 AND 2 AND b=3;', 1),
                ('SELECT id FROM t WHERE 1=1 AND a=1 AND b=2;', 1),
                ('SELECT id FROM t WHERE 1=1 and a=1;', 1),
                ('SELECT id FROM t WHERE id IN (SELECT x FROM u WHERE a=1 AND b=2);', 1)):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first.count('WHERE 1=1'), count)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

if __name__ == "__main__":
    unittest.main()
