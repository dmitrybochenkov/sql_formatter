"""Synthetic regression coverage for local/procedural DML coordinates."""
import unittest
from itertools import cycle

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_procedure import local_dml_fragment, indented_fragment, ProcedureRefusal
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_protection import protected_spans
from dbeaver_adapter import PROFILE_FORMATTERS
from tests.unit.test_procedure_prototype import wrap, walk


class ProceduralDmlIndentationTests(unittest.TestCase):
    def check(self, sql):
        diagnostics = []
        result = format_sql(sql, diagnostics=diagnostics)
        self.assertEqual(diagnostics, [])
        validate_sql_unchanged(sql, result)
        self.assertEqual([(p.kind, sql[p.start:p.end]) for p in protected_spans(sql)],
                         [(p.kind, result[p.start:p.end]) for p in protected_spans(result)])
        for _ in range(2):
            diagnostics = []
            self.assertEqual(format_sql(result, diagnostics=diagnostics), result)
            self.assertEqual(diagnostics, [])
        return result

    def test_lists_keep_relative_continuation_columns(self):
        for op in ('IN', 'NOT IN'):
            sql = wrap('INSERT INTO t SELECT a FROM u WHERE a '+op+' (1,\n  2,\n      3);')
            result = self.check(sql)
            self.assertIn('(1,\n      2,\n          3)', result)

    def test_sequential_inserts_and_nested_blocks_loops(self):
        dml = 'INSERT INTO t SELECT a FROM u WHERE a IN (1,\n  2);'
        sql = wrap(dml+' BEGIN '+dml+' WHILE a<3 DO '+dml+' SET a=a+1; END WHILE; END; '+dml)
        result = self.check(sql)
        self.assertEqual(result.count('INSERT INTO t'), 4)
        self.assertIn('(1,\n      2)', result)
        self.assertIn('(1,\n          2)', result)
        self.assertIn('(1,\n              2)', result)

    def test_expressions_nested_parentheses_functions_and_comments(self):
        sql = wrap("INSERT INTO t SELECT a FROM u WHERE (COALESCE(a,\n  1)>0 OR (b=2\n    AND c=3)); -- keep\nINSERT INTO t SELECT a FROM u WHERE a IN (1,\n  2 /* item */,\n    3);")
        result = self.check(sql)
        self.assertIn('/* item */', result)
        self.assertIn('-- keep', result)

    def test_protected_multiline_values_and_mixed_endings(self):
        source = wrap('INSERT INTO t SELECT \'x\r\ny\rz\' AS "q\r\ns" FROM u WHERE a IN (1,\n  2); /* c\r\nd\re */\nDELETE FROM t WHERE a IN (1,\n  2);')
        # Replace only unprotected LF, preserving every protected byte.
        spans = protected_spans(source)
        for endings in (('\n',), ('\r',), ('\r\n',), ('\r\n', '\n', '\r')):
            endings = cycle(endings)
            sql = '\ufeff'+''.join(next(endings) if ch=='\n' and not any(p.start<=i<p.end for p in spans) else ch
                                   for i,ch in enumerate(source))
            result = self.check(sql)
            self.assertTrue(result.startswith('\ufeff'))
            self.assertNotEqual(result, sql)

    def test_both_profiles_have_identical_successful_results(self):
        raw = ('\ufeff'+wrap('INSERT INTO T SELECT A FROM U WHERE A NOT IN (1,\r\n  2);')).encode()
        results = []
        for route in PROFILE_FORMATTERS.values():
            result = route(raw)
            self.assertNotEqual(result, raw)
            self.assertEqual(route(result), result)
            results.append(result)
        self.assertEqual(results[0], results[1])

    def test_outer_margin_inverse_preserves_opaque_and_blank_lines(self):
        raw = "INSERT INTO t SELECT 'a\nb' AS s FROM u WHERE a IN (1, /* x\ny */\n  2,\n    \n      3)"
        nested = indented_fragment(raw, 8)
        sql = 'CREATE PROCEDURE p() BEGIN\n        '+nested+'; END;'
        parsed = source_linter().parse_string(sql)
        self.assertEqual(parsed.violations, [])
        node = next(n for n in walk(parsed.tree) if n.is_type('insert_statement'))
        self.assertEqual(local_dml_fragment(sql, node), raw)

    def test_ambiguous_insufficient_margin_keeps_atomic_refusal(self):
        sql = 'CREATE PROCEDURE p() BEGIN\n        INSERT INTO t SELECT a FROM u WHERE a IN (1,\n  2); END;'
        parsed = source_linter().parse_string(sql)
        node = next(n for n in walk(parsed.tree) if n.is_type('insert_statement'))
        with self.assertRaises(ProcedureRefusal):
            local_dml_fragment(sql, node)
        ds = []
        self.assertEqual(format_sql(sql, diagnostics=ds), sql)
        self.assertIn('SQLFMT-E003', [d.code for d in ds])
