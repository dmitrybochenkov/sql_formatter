"""Request-local value reuse must never weaken proof comparisons or isolation."""
import contextvars
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from formatter_modules.formatter_request import request_scope, proof_memo, _CURRENT


class RequestProofTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.config = Path(self.directory.name) / 'config'
        self.config.write_bytes(b'one')
        self.calls = []

        @proof_memo(lambda: self.config)
        def compute(sql):
            self.calls.append(sql)
            return {'tokens': [sql], 'permissions': {1}}
        self.compute = compute

    def test_nested_scope_reuse_returns_defensive_values(self):
        @request_scope
        def nested():
            return self.compute('x')
        @request_scope
        def run():
            first = self.compute('x')
            first['tokens'].clear()
            first['permissions'].clear()
            second = nested()
            self.assertEqual(second, {'tokens': ['x'], 'permissions': {1}})
            second['tokens'].append('changed')
            self.assertEqual(nested()['tokens'], ['x'])
        run()
        self.assertEqual(self.calls, ['x'])
        self.assertIsNone(_CURRENT.get())

    def test_lifetime_new_request_and_no_implicit_cache(self):
        @request_scope
        def run():
            self.compute('x'); self.compute('x')
        run(); run(); self.compute('x'); self.compute('x')
        self.assertEqual(len(self.calls), 4)

    def test_exact_source_endings_and_configuration_changes(self):
        @request_scope
        def run():
            for sql in ('x', 'X', 'x\n', 'x\r', 'x\r\n'):
                self.compute(sql)
            self.compute('x')
            self.config.write_bytes(b'two')
            self.compute('x')
        run()
        self.assertEqual(len(self.calls), 6)

    def test_exceptions_are_not_cached_and_scope_clears(self):
        calls=[]
        @proof_memo(lambda: self.config)
        def failing(sql):
            calls.append(sql)
            raise ValueError('synthetic')
        @request_scope
        def run():
            self.compute('x')
            for _ in range(2):
                with self.assertRaises(ValueError): failing('x')
            raise RuntimeError('stop')
        with self.assertRaises(RuntimeError): run()
        self.assertEqual(calls, ['x', 'x'])
        self.assertIsNone(_CURRENT.get())

    def test_threads_and_copied_context_cannot_share_active_store(self):
        @request_scope
        def run():
            self.compute('x')
            copied=contextvars.copy_context()
            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(copied.run, request_scope(lambda: self.compute('x'))).result()
            self.compute('x')
            return contextvars.copy_context()
        expired=run()
        expired.run(request_scope(lambda: self.compute('x')))
        self.assertEqual(len(self.calls), 3)

    def test_cache_limits_bypass_without_altering_values(self):
        @request_scope
        def run():
            for i in range(4):
                self.assertEqual(self.compute(str(i))['tokens'], [str(i)])
            self.compute('3')
            self.compute('large'); self.compute('large')
        with patch('formatter_modules.formatter_request._MAX_ENTRIES',2), patch(
                'formatter_modules.formatter_request._MAX_ENTRY_CHARS',3): run()
        self.assertEqual(len(self.calls), 7)

    def test_unreadable_fingerprint_does_not_add_a_new_failure(self):
        @request_scope
        def run():
            with patch.object(Path,'read_bytes',side_effect=PermissionError('synthetic')):
                self.assertEqual(self.compute('x')['tokens'], ['x'])
                self.assertEqual(self.compute('x')['tokens'], ['x'])
            self.assertEqual(_CURRENT.get().values, {})
        run()
        self.assertEqual(self.calls, ['x','x'])

    def test_total_source_budget_is_bounded(self):
        @request_scope
        def run():
            self.compute('a')
            self.compute('bb'); self.compute('bb')
            self.compute('a')
            self.assertEqual(_CURRENT.get().source_chars, 1)
        with patch('formatter_modules.formatter_request._MAX_SOURCE_CHARS',2): run()
        self.assertEqual(self.calls, ['a','bb','bb'])

    def test_validator_still_rejects_mutations_after_valid_cache_hit(self):
        from formatter import validate_sql_unchanged
        @request_scope
        def run():
            source="SELECT a.id AS x FROM t AS a WHERE a.id>0 AND a.id<5;"
            good=source.replace('t AS a','t a')
            validate_sql_unchanged(source,good)
            validate_sql_unchanged(source,good)
            for bad in (good.replace('>0','>1'),good.replace('AS x','AS y'),
                        good.replace('WHERE','WHERE 1=1 AND 1=1 AND')):
                with self.assertRaises(ValueError): validate_sql_unchanged(source,bad)
            quoted="SELECT 'x\r\ny' FROM t;"
            validate_sql_unchanged(quoted,quoted)
            with self.assertRaises(ValueError):
                validate_sql_unchanged(quoted,quoted.replace('\r\n','\n'))
        run()

    def test_sequential_profiles_sql_and_rollback_are_isolated(self):
        from dbeaver_adapter import PROFILE_FORMATTERS
        sources=[b'select a from t;', b'SELECT ROW_NUMBER() OVER win FROM t;',
                 b'SELECT b FROM u;', b'SELECT \'x\r\ny\' FROM t;']
        for source in sources:
            outputs=[fn(source) for fn in PROFILE_FORMATTERS.values()]
            self.assertEqual(outputs[0],outputs[1])
            for fn in PROFILE_FORMATTERS.values():
                self.assertEqual(fn(outputs[0]),outputs[0])
            self.assertIsNone(_CURRENT.get())

    def test_formatting_still_runs_procedure_repeat(self):
        from formatter import format_sql
        import formatter_modules.formatter_procedure as procedure
        source='CREATE PROCEDURE p() BEGIN INSERT INTO t SELECT a FROM u; END;'
        original=procedure.format_procedure
        checks=[]
        def track(*args,**kwargs):
            checks.append(kwargs.get('_checking',False))
            return original(*args,**kwargs)
        with patch.object(procedure,'format_procedure',side_effect=track):
            result=format_sql(source,diagnostics=[])
        self.assertIn(True,checks)
        self.assertEqual(format_sql(result,diagnostics=[]),result)
