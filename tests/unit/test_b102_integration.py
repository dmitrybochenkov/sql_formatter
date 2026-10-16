import unittest
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_case import normalize_case
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_dialect import is_procedure
from tests.unit.test_procedure_prototype import walk


class GrammarIntegrationTests(unittest.TestCase):
    def test_header_selection_is_lexical(self):
        for s in ("SELECT 'CREATE PROCEDURE' FROM t;", '-- REPLACE PROCEDURE\nSELECT a FROM t;'):
            self.assertFalse(is_procedure(s))
        self.assertTrue(is_procedure('-- note\nreplace procedure p() begin end;'))

    def test_runtime_and_case_share_grammar_and_source_map(self):
        sql = "replace procedure P()\r\nbegin\rdeclare V varchar(30);\rset V='X\r\nY';\nend;"
        tree = source_linter().parse_string(sql).tree
        self.assertEqual(tree.raw, sql)
        self.assertFalse(any(n.is_type('unparsable') for n in walk(tree)))
        for n in walk(tree):
            if not n.is_meta and n.pos_marker:
                self.assertEqual(sql[n.pos_marker.source_slice], n.raw)
        normalized = normalize_case(sql)
        self.assertIn('REPLACE PROCEDURE p()', normalized)
        self.assertIn("'X\r\nY'", normalized)
        self.assertEqual(normalize_case(normalized), normalized)

    def test_dml_combinations(self):
        for sql in (
            'INSERT INTO t SELECT id, name FROM u WHERE a=1 AND b=2;',
            'INSERT INTO t\n        SELECT a.id FROM a\n        JOIN b ON a.id=b.id\n        WHERE a.id IN (SELECT id FROM c);',
            'DELETE FROM t WHERE a=1;',
            "DELETE FROM t WHERE a='x' OR b='y';",
            'DELETE FROM t WHERE id IN (SELECT id FROM u WHERE a=1 AND b=2);',
            "INSERT INTO t SELECT a.id FROM a JOIN b ON a.id=b.id AND b.s='OK';",
        ):
            with self.subTest(sql=sql):
                diagnostics=[]
                result=format_sql(sql, diagnostics=diagnostics)
                validate_sql_unchanged(sql,result)
                self.assertEqual(format_sql(result,diagnostics=[]),result)
                self.assertEqual(diagnostics,[])
