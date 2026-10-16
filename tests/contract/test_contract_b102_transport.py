import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dbeaver_adapter as adapter
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_edits import Edit
from formatter_modules.formatter_protection import protected_spans
from tests.adapter_runner import adapter_command
from tests.contract.test_contract_b102 import SIMPLE_INPUT, SIMPLE_EXPECTED
from tests.unit.test_procedure_prototype import wrap

ROOT=Path(__file__).resolve().parents[2]


class ProcedureTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='procedure integration ')
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1', SQL_FORMATTER_LOG_DIR=str(self.base/'logs'))
        self.patch=patch.dict(os.environ,self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_profiles_endings_bom_and_idempotence(self):
        for ending in ('\n','\r','\r\n','\r\n\n\r'):
            for profile in adapter.PROFILE_FORMATTERS:
                with self.subTest(ending=repr(ending),profile=profile):
                    raw=b'\xef\xbb\xbf'+SIMPLE_INPUT.replace(' begin ',ending+'begin'+ending).encode()
                    expected=b'\xef\xbb\xbf'+SIMPLE_EXPECTED.encode()
                    with patch('dbeaver_profile_selector.select_profile',return_value=profile):
                        result=adapter.select_and_format_bytes(raw)
                        self.assertEqual(result,expected)
                        self.assertEqual(adapter.select_and_format_bytes(result),result)

    def test_merged_adapter_subprocess_and_arbitrary_cwd(self):
        path=self.base/'процедура с пробелами.sql'
        # Hostile local config must not change the absolute project config.
        (self.base/'.sqlfluff').write_text('[sqlfluff]\ndialect = sqlite\n')
        raw=b'\xef\xbb\xbf'+SIMPLE_INPUT.encode()
        for profile in ('personal','corporate','cancel'):
            path.write_bytes(raw)
            result=subprocess.run(adapter_command(ROOT/'dbeaver_adapter.py',path,profile),
                cwd=self.base,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
            self.assertEqual(result.returncode,0)
            self.assertEqual(result.stdout,raw if profile=='cancel' else b'\xef\xbb\xbf'+SIMPLE_EXPECTED.encode())
            self.assertEqual(path.read_bytes(),raw)

    def test_cli_no_gui_success_and_failure_bytes(self):
        path=self.base/'SQL.sql'
        invalid=wrap('IF a=1 THEN SET a=2; END IF;')+'\r\n'
        for script in ('formatter.py','dbeaver_formatter.py'):
            for source, expected in ((SIMPLE_INPUT,SIMPLE_EXPECTED),(invalid,invalid)):
                path.write_bytes(b'\xef\xbb\xbf'+source.encode())
                # Importing tkinter fails deliberately: both CLIs must be headless.
                command=[sys.executable,'-c',
                    'import sys,runpy; sys.modules["tkinter"]=None; '
                    'sys.path.insert(0,sys.argv[1]); script=sys.argv.pop(1)+"/"+sys.argv.pop(1); '
                    'sys.argv[0]=script; runpy.run_path(script,run_name="__main__")',
                    str(ROOT),script,str(path)]
                result=subprocess.run(command,cwd=self.base,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertEqual(result.stdout,b'\xef\xbb\xbf'+expected.encode())
                if source==SIMPLE_INPUT:
                    self.assertEqual(result.stderr,b'')

    def test_invalid_ambiguous_and_e004_original_bytes(self):
        cases=[wrap('WHILE a<2 DO SET a=1; END;'),
               wrap('SET a=1;\n-- detached\n\nCALL p();'),
               wrap('INSERT INTO t SELECT SUM(a) OVER w FROM u;'),
               wrap('SET a=SUM(b) OVER w;')]
        for sql in cases:
            raw=b'\xef\xbb\xbf'+sql.replace('\n','\r\n').encode()
            self.assertEqual(adapter.format_bytes(raw),raw)
            self.assertEqual(adapter.format_bytes(adapter.format_bytes(raw)),raw)
        ds=[]
        self.assertEqual(format_sql(cases[-1],diagnostics=ds),cases[-1])
        self.assertIn('SQLFMT-E004',[d.code for d in ds])

    def test_protected_multiline_bytes_and_validator_negative(self):
        source=wrap('DECLARE "a\r\nb" VARCHAR(80); SET "a\r\nb"=\'X\rY\'; /* C\r\nD */\nCALL p(\'DO; END\');')
        raw=b'\xef\xbb\xbf'+source.encode()
        result=adapter.format_bytes(raw)
        self.assertNotEqual(result,raw)
        self.assertTrue(result.startswith(b'\xef\xbb\xbf'))
        decoded=result.decode('utf-8-sig')
        validate_sql_unchanged(source,decoded)
        self.assertEqual(adapter.format_bytes(result),result)
        for value in (decoded.replace('C\r\nD','C\nD'),decoded.replace('X\rY','X\nY'),
                      decoded.replace('a\r\nb','a\nb'),decoded.replace('C\r\nD','C\r\r\nD')):
            with self.assertRaises(ValueError):
                validate_sql_unchanged(source,value)

    def test_actual_conflicts_and_protected_ranges_abort_transaction(self):
        from formatter_modules.formatter_edits import plan_edits as real_plan
        def injected(source,edits,protected=()):
            all_edits=list(edits)
            first=all_edits[0]
            all_edits.append(Edit(first.start,first.end,'X','INJECT','test','procedure'))
            return real_plan(source,all_edits,protected)
        with patch('formatter_modules.formatter_procedure.plan_edits',side_effect=injected):
            ds=[]
            self.assertEqual(format_sql(SIMPLE_INPUT,diagnostics=ds),SIMPLE_INPUT)
            self.assertIn('SQLFMT-E001',[d.code for d in ds])
        def protected_edit(source,edits,protected=()):
            span=next(p for p in protected_spans(source) if p.kind=='literal')
            return real_plan(source,list(edits)+[Edit(span.start,span.end,"'changed'",'INJECT','test','procedure')],protected)
        with patch('formatter_modules.formatter_procedure.plan_edits',side_effect=protected_edit):
            ds=[]
            self.assertEqual(format_sql(SIMPLE_INPUT,diagnostics=ds),SIMPLE_INPUT)
            self.assertIn('SQLFMT-E002',[d.code for d in ds])

    def test_execution_scopes_and_prefixes_stay_separate(self):
        source=wrap("DELETE FROM t WHERE a=1 AND b=2; WHILE a<3 DO DELETE FROM u WHERE c=1; SET a=a+1; END WHILE;")
        result=format_sql(source,diagnostics=[])
        self.assertEqual(result.count('WHERE 1=1'),1)
        validate_sql_unchanged(source,result)
        with self.assertRaises(ValueError):
            validate_sql_unchanged(source,result.replace('WHERE c = 1','WHERE 1=1 AND c = 1'))
        with self.assertRaises(ValueError):
            validate_sql_unchanged(source,result.replace('WHILE a < 3','WHILE 1=1 AND a < 3'))
        self.assertEqual(format_sql(result,diagnostics=[]),result)

    def test_bom_cannot_be_removed_by_validator(self):
        result='\ufeff'+SIMPLE_EXPECTED
        validate_sql_unchanged('\ufeff'+SIMPLE_INPUT,result)
        with self.assertRaises(ValueError):
            validate_sql_unchanged('\ufeff'+SIMPLE_INPUT,result[1:])

    def test_unstable_nested_layout_refuses_whole_procedure(self):
        from formatter_modules.formatter_procedure import format_procedure
        sql=wrap('INSERT INTO t SELECT a FROM u;')
        calls=[]
        def unstable(source,diagnostics):
            result=format_sql(source,diagnostics=diagnostics)
            calls.append(source)
            return result if len(calls)==1 else result.replace('\nFROM','\n\nFROM')
        ds=[]
        self.assertEqual(format_procedure(sql,unstable,validate_sql_unchanged,ds),sql)
        self.assertEqual(len(calls),2)
        self.assertIn('SQLFMT-E003',[d.code for d in ds])

    def test_dml_literals_comments_and_long_in_lists(self):
        sql=wrap("INSERT INTO t SELECT 'A\r\nB' AS s, a FROM u WHERE a IN (1,2,3,4,5,6,7,8,9,10) AND b NOT IN (11,12,13); DELETE FROM t WHERE s='X\rY';")
        ds=[]
        result=format_sql(sql,diagnostics=ds)
        self.assertEqual(ds,[])
        self.assertNotEqual(result,sql)
        validate_sql_unchanged(sql,result)
        self.assertEqual(format_sql(result,diagnostics=[]),result)
