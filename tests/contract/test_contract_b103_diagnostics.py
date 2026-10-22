"""Synthetic diagnosis only: no corporate input or object names in the suite."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_procedure import format_procedure
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_trace import event
from tests.unit.test_procedure_prototype import wrap, walk
from tests.adapter_runner import adapter_command

ROOT=Path(__file__).resolve().parents[2]
REPRO=wrap('INSERT INTO t SELECT a FROM u WHERE a IN (1,\n2);')


class B103DiagnosisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base=Path(self.temp.name)
        self.env={'SQL_FORMATTER_TRACE':'1','SQL_FORMATTER_LOG_DIR':str(self.base/'logs')}
        self.patcher=patch.dict(os.environ,self.env)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def records(self):
        return [json.loads(s) for s in (self.base/'logs/diagnostic.jsonl').read_text().splitlines()]

    def test_known_multiline_in_reproduces_atomic_rollback(self):
        ds=[]
        self.assertEqual(format_sql(REPRO,diagnostics=ds),REPRO)
        self.assertEqual([d.code for d in ds],['SQLFMT-E003'])
        records=self.records()
        mismatch=next(r for r in records if r['code']=='NON_IDEMPOTENT')
        self.assertEqual(mismatch['stage'],'repeat')
        self.assertEqual(mismatch['view'],'candidate')
        self.assertEqual(mismatch['segment'],'procedure_definition')
        self.assertTrue(any(r['stage']=='validate' and r['code']=='END' for r in records))
        self.assertEqual(records[-1]['stage'],'rollback')
        for ending in ('\r', '\r\n', '\r\n\n\r'):
            variant='\ufeff'+REPRO.replace('\n',ending)
            self.assertEqual(format_sql(variant,diagnostics=[]),variant)
        # Internal one-pass probe only: public fail-safe is never bypassed.
        first=format_procedure(REPRO,format_sql,validate_sql_unchanged,[],_checking=True)
        second=format_procedure(first,format_sql,validate_sql_unchanged,[],_checking=True)
        self.assertIn('\n    2)',first)
        self.assertIn('\n        2)',second)
        self.assertEqual(second,first.replace('\n    2)','\n        2)'))
        validate_sql_unchanged(REPRO,first)
        validate_sql_unchanged(REPRO,second)

    def test_synthetic_construct_matrix(self):
        stable=[
            'CREATE PROCEDURE p() SQL SECURITY INVOKER /* header */ BEGIN SET a=1; END;',
            wrap("SET a=CAST('2000-01-01' AS TIMESTAMP(6));"),
            wrap("SET a=INTERVAL '1' SECOND;"),
            wrap("CALL p(TO_CHAR(a)||'x', COALESCE(a,b));"),
            wrap('DELETE FROM t WHERE (a=1 OR b=2) AND c BETWEEN 1 AND 3;'),
            wrap('INSERT INTO t SELECT a FROM u; INSERT INTO t SELECT b FROM v;'),
            wrap('INSERT INTO t SELECT a FROM u WHERE a NOT IN ('+','.join(map(str,range(50)))+');'),
            wrap('INSERT INTO t SELECT a FROM u WHERE a IN ('+','.join(map(str,range(50)))+');'),
        ]
        unstable=[wrap('INSERT INTO t SELECT a FROM u WHERE a '+op+' (1,\n2,\n3);')
                  for op in ('IN','NOT IN')]
        for sql in stable+unstable:
            with self.subTest(sql=sql):
                parsed=source_linter().parse_string(sql)
                self.assertEqual(parsed.violations,[])
                self.assertFalse(any(n.is_type('unparsable') for n in walk(parsed.tree)))
                ds=[];result=format_sql(sql,diagnostics=ds)
                if sql in unstable:
                    self.assertEqual(result,sql)
                    self.assertEqual([d.code for d in ds],['SQLFMT-E003'])
                else:
                    self.assertEqual(ds,[])
                    self.assertNotEqual(result,sql)
                    validate_sql_unchanged(sql,result)
                    self.assertEqual(format_sql(result,diagnostics=[]),result)

    def test_tracing_is_opt_in_and_does_not_change_result(self):
        path=self.base/'logs/diagnostic.jsonl'
        with patch.dict(os.environ,SQL_FORMATTER_TRACE='0'):
            first=format_sql(REPRO,diagnostics=[])
        self.assertFalse(path.exists())
        self.assertEqual(format_sql(REPRO,diagnostics=[]),first)
        # An unwritable log destination must not interfere with rollback.
        bad=self.base/'file';bad.write_text('x')
        with patch.dict(os.environ,SQL_FORMATTER_LOG_DIR=str(bad)):
            self.assertEqual(format_sql(REPRO,diagnostics=[]),first)

    def test_logs_and_streams_never_include_payload(self):
        secret='sensitive_marker_qqq'
        sql=wrap("CALL "+secret+"('"+secret+"');")
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            format_sql(sql,diagnostics=[])
            event(secret,secret)  # Reject arbitrary strings instead of logging them.
        self.assertEqual(out.getvalue()+err.getvalue(),'')
        text=(self.base/'logs/diagnostic.jsonl').read_text()
        self.assertNotIn(secret,text)
        allowed={'time','pid','stage','code','segment','line','offset','view','elapsed_ms','error_type'}
        self.assertTrue(all(set(r)<=allowed for r in self.records()))

    def test_headless_diagnostic_and_merged_adapter(self):
        path=self.base/'sample.sql';raw=b'\xef\xbb\xbf'+REPRO.replace('\n','\r\n').encode()
        path.write_bytes(raw)
        for profile in ('personal','corporate'):
            env=dict(os.environ)
            command=[sys.executable,str(ROOT/'diagnose_formatter.py'),str(path),profile,str(self.base/'logs')]
            run=subprocess.run(command,cwd=self.base,env=env,capture_output=True,timeout=60)
            self.assertEqual(run.returncode,0)
            self.assertEqual(run.stdout+run.stderr,b'')
            run=subprocess.run(adapter_command(ROOT/'dbeaver_adapter.py',path,profile),
                cwd=self.base,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            self.assertEqual(run.returncode,0)
            self.assertEqual(run.stdout,raw)
            self.assertEqual(path.read_bytes(),raw)

    def test_stage_of_grammar_failure_is_distinct(self):
        sql=wrap('IF a=1 THEN SET a=2; END IF;')
        self.assertEqual(format_sql(sql,diagnostics=[]),sql)
        records=self.records()
        self.assertTrue(any(r['stage']=='parse' and r['code']=='UNPARSABLE' for r in records))
        self.assertFalse(any(r['stage']=='case' for r in records))
