"""New procedure goldens; old SQL goldens remain untouched."""
import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_edits import Diagnostic
from formatter_modules.formatter_protection import protected_spans
from tests.unit.test_procedure_prototype import SYNTHETIC, wrap


SIMPLE_INPUT = "replace procedure P(in D date) sql security invoker begin declare V date; set V=D; while V<D+2 do call LOG_P('DO; END --',V); set V=V+1; end while; end;"
SIMPLE_EXPECTED = """REPLACE PROCEDURE p(
    IN d DATE
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v DATE;

    SET v = d;

    WHILE v < d + 2 DO
        CALL log_p(
            'DO; END --'
            , v
        );

        SET v = v + 1;
    END WHILE;
END;
"""


class ProcedureLayoutTests(unittest.TestCase):
    def check(self, sql, expected=None):
        ds=[]
        result=format_sql(sql,diagnostics=ds)
        self.assertEqual(ds, [])
        if expected is not None:
            self.assertEqual(result,expected)
        validate_sql_unchanged(sql,result)
        second_ds=[]
        self.assertEqual(format_sql(result,diagnostics=second_ds),result)
        self.assertEqual(second_ds,[])
        self.assertEqual([(p.kind,sql[p.start:p.end]) for p in protected_spans(sql)],
                         [(p.kind,result[p.start:p.end]) for p in protected_spans(result)])
        return result

    def test_simple_golden(self):
        self.check(SIMPLE_INPUT,SIMPLE_EXPECTED)

    def test_nested_blocks_and_consecutive_loops(self):
        sql=wrap('BEGIN DECLARE x INTEGER; SET x=1; END; WHILE a<2 DO WHILE b<2 DO SET b=b+1; END WHILE; SET a=a+1; END WHILE; WHILE c<2 DO SET c=c+1; END WHILE;')
        result=self.check(sql)
        self.assertIn('        WHILE b < 2 DO\n            SET b = b + 1;\n        END WHILE;',result)
        self.assertEqual(result.count('\n    WHILE'),2)
        self.assertIn('    BEGIN\n        DECLARE x INTEGER;\n\n        SET x = 1;\n    END;',result)

    def test_full_synthetic_and_dml_depth(self):
        result=self.check(SYNTHETIC)
        self.assertIn('        INSERT INTO example_target\n        SELECT\n            a.id',result)
        self.assertIn('        INNER JOIN example_other b\n        ON a.id = b.id',result)
        self.assertIn('        WHERE 1=1\n            AND a.event_date',result)
        self.assertIn('                SELECT\n                    id',result)
        self.assertIn("'Processing; -- DO END'",result)

    def test_comments_remain_attached(self):
        sql=wrap("SET a=1; -- first\n-- next call\nCALL p('x'); /* trailing */\nSET a=2;")
        result=self.check(sql)
        self.assertIn('SET a = 1; -- first\n    -- next call\n    CALL',result)
        self.assertIn("); /* trailing */\n    SET",result)
        headed=self.check('-- procedure\n       '+SIMPLE_INPUT)
        self.assertTrue(headed.startswith('-- procedure\nREPLACE PROCEDURE'))

    def test_multiline_protected_and_endings(self):
        sql=wrap('DECLARE "a\r\nb" VARCHAR(100); SET "a\r\nb"=\'x\ry\'; /* z\r\nq */\nCALL p(\'-- END;\');')
        for ending in ('\n','\r','\r\n'):
            with self.subTest(ending=repr(ending)):
                # Change only the existing outside LF after the block comment.
                source=sql.replace('*/\n','*/'+ending)
                result=self.check(source)
                spans=protected_spans(result)
                self.assertTrue(all(any(p.start<=i<p.end for p in spans)
                                    for i,c in enumerate(result) if c=='\r'))

    def test_one_line_and_indented_inputs_equal(self):
        self.check(SIMPLE_EXPECTED, SIMPLE_EXPECTED)
        source=SIMPLE_EXPECTED.replace('\n','\n       ')
        self.check(source,SIMPLE_EXPECTED)
        self.check(SIMPLE_INPUT.replace('in D date','in\n      D\n  date'),SIMPLE_EXPECTED)

    def test_ambiguous_comment_returns_entire_original(self):
        sql='\ufeff'+wrap('SET a=1;\r\n-- detached\r\n\r\nCALL p();')
        for _ in range(2):
            ds=[]
            self.assertEqual(format_sql(sql,diagnostics=ds),sql)
            self.assertIn('SQLFMT-C001',[d.code for d in ds])

        for call in ("CALL p(a, -- attached to a\nb);", "CALL p(a, /* attached */ b);"):
            source=wrap(call)
            ds=[]
            self.assertEqual(format_sql(source,diagnostics=ds),source)
            self.assertIn('SQLFMT-C001',[d.code for d in ds])

    def test_invalid_or_unsupported_returns_entire_original(self):
        for sql in (wrap('IF a=1 THEN SET a=2; END IF;'), wrap('CALL p(1,);'),
                    wrap('SET a=1;')[:-4],wrap('DECLARE x CURSOR FOR SELECT a FROM t;')):
            ds=[]
            self.assertEqual(format_sql(sql,diagnostics=ds),sql)
            self.assertIn('SQLFMT-E003',[d.code for d in ds])

    def test_no_partial_edits_on_planner_failure(self):
        warning=Diagnostic('SQLFMT-E002',1,'test protected conflict')
        with patch('formatter_modules.formatter_procedure.plan_edits',return_value=([],[warning])):
            ds=[]
            self.assertEqual(format_sql(SIMPLE_INPUT,diagnostics=ds),SIMPLE_INPUT)
            self.assertIn('SQLFMT-E002',[d.code for d in ds])

    def test_validator_rejects_structural_and_token_changes(self):
        source=wrap('SET a=1; WHILE a<2 DO SET a=a+1; END WHILE;')
        invalid=[wrap('WHILE a<2 DO SET a=1; SET a=a+1; END WHILE;'),
                 source.replace('a+1','a+2'), source.replace('SET a=1;',''),
                 source.replace('END WHILE;','END;'),
                 source.replace('SET a=1;','SET a=1;;')]
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_sql_unchanged(source,value)

    def test_failure_of_nested_formatter_rolls_back_whole_procedure(self):
        from formatter_modules.formatter_procedure import format_procedure
        sql=wrap('SET a=1; INSERT INTO t SELECT a FROM u;')
        with patch('formatter_modules.formatter_procedure.normalize_case',side_effect=ValueError('test')):
            ds=[]
            self.assertEqual(format_sql(SIMPLE_INPUT,diagnostics=ds),SIMPLE_INPUT)
        ds=[]
        def failure(*a,**k): raise ValueError('private SQL must not leak')
        self.assertEqual(format_procedure(sql,failure,validate_sql_unchanged,ds),sql)
        self.assertTrue(all('private' not in d.message for d in ds))
