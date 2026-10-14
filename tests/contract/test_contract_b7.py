import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import dbeaver_adapter as adapter
from formatter import format_sql, validate_sql_unchanged

ROOT = Path(__file__).resolve().parents[2]


class B7AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='sql formatter ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
                        SQL_FORMATTER_LOG_DIR=str(self.base / 'logs'))
        self.patch = patch.dict(os.environ, self.env)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def run_adapter(self, raw, script=None, merge=False):
        path = self.base / 'запрос с пробелом.sql'
        path.write_bytes(raw)
        result = subprocess.run([sys.executable, str(script or ROOT / 'dbeaver_adapter.py'), str(path)],
                                cwd=self.base, env=self.env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT if merge else subprocess.PIPE, timeout=30)
        self.assertEqual(path.read_bytes(), raw)
        self.assertEqual(result.returncode, 0, result.stderr)
        if not merge:
            self.assertEqual(result.stderr, b'')
        return result.stdout

    def test_success_exact_and_repeat(self):
        source = b'SELECT id, name FROM users WHERE active=1;'
        expected = b'SELECT\n    id\n    , name\nFROM users\n\nWHERE active = 1\n;\n'
        for merge in (False, True):
            first = self.run_adapter(source, merge=merge)
            self.assertEqual(first, expected)
            self.assertEqual(self.run_adapter(first, merge=merge), first)

    def test_failures_return_original_with_bom_and_endings(self):
        for raw in (b'\xef\xbb\xbfSELECT FROM;\r\n',
                    b'\xef\xbb\xbfSELECT SUM(a) OVER w\rFROM t;\r\n', b'\xff\xfeinvalid'):
            for merge in (False, True):
                self.assertEqual(self.run_adapter(raw, merge=merge), raw)

    def test_unicode_protected_endings(self):
        for ending in ('\n', '\r', '\r\n', '\r\n\n\r'):
            source = f'SELECT{ending}\'Привет\r\n世界\' AS "имя\rполе" /* x\ry\r\nz */ FROM t;'
            raw = b'\xef\xbb\xbf' + source.encode()
            first = self.run_adapter(raw, merge=True)
            validate_sql_unchanged(source, first.decode())
            self.assertEqual(first, format_sql(source, diagnostics=[]).encode())
            self.assertEqual(self.run_adapter(first), first)

    def test_warning_result_is_validated_and_logged(self):
        source = 'SELECT SUM(a) OVER (PARTITION BY a,\r\n-- detached\r\n\r\nb) AS n FROM t;'
        first = self.run_adapter(source.encode(), merge=True)
        validate_sql_unchanged(source, first.decode())
        self.assertEqual(self.run_adapter(first), first)
        events = (self.base / 'logs/adapter.jsonl').read_text()
        self.assertIn('SQLFMT-C001', events)
        self.assertIn('SQLFMT-E002', events)
        self.assertNotIn('detached', events)
        self.assertNotIn(source, events)

    def test_exception_and_unexpected_output_are_quiet(self):
        raw = b'\xef\xbb\xbfSELECT a FROM t;\r'
        def noisy(*args, **kwargs):
            print('SECRET SQL', file=sys.stderr)
            print('SECRET SQL', file=sys.stdout)
            raise RuntimeError('SECRET SQL')
        out, err = io.StringIO(), io.StringIO()
        with patch('formatter.format_sql', side_effect=noisy), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            self.assertEqual(adapter.format_bytes(raw), raw)
        self.assertEqual(out.getvalue() + err.getvalue(), '')
        self.assertNotIn('SECRET', (self.base / 'logs/adapter.jsonl').read_text())
        with patch('formatter.format_sql', return_value='SELECT b FROM t;'):
            self.assertEqual(adapter.format_bytes(raw), raw)

    def test_log_failure_does_not_change_output(self):
        path = self.base / 'not a directory'
        path.write_bytes(b'occupied')
        self.env['SQL_FORMATTER_LOG_DIR'] = str(path)
        raw = b'SELECT SUM(a) OVER w FROM t;\r'
        self.assertEqual(self.run_adapter(raw, merge=True), raw)
        with patch.object(Path, 'mkdir', side_effect=PermissionError('secret')):
            adapter.log_event('ADAPTER-READ', 'ReadError')

    def test_read_and_argument_errors_never_emit_diagnostics(self):
        for args in ([], [str(self.base / 'missing')], [str(self.base)], ['a', 'b']):
            result = subprocess.run([sys.executable, str(ROOT / 'dbeaver_adapter.py'), *args],
                                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')

    def test_paths_foreign_configuration_and_import(self):
        project = self.base / 'проект с пробелами'
        project.mkdir()
        for name in ('formatter.py', 'dbeaver_adapter.py', 'dbeaver_formatter.py', '.sqlfluff'):
            shutil.copy(ROOT / name, project / name)
        shutil.copytree(ROOT / 'formatter_modules', project / 'formatter_modules',
                        ignore=shutil.ignore_patterns('__pycache__'))
        (self.base / '.sqlfluff').write_text('[sqlfluff]\ndialect=ansi\ntemplater=jinja\n')
        raw = b'SELECT a FROM t;'
        self.assertEqual(self.run_adapter(raw, project / 'dbeaver_adapter.py'),
                         b'SELECT\n    a\nFROM t\n;\n')
        code = ('import sys; before=(sys.stdout,sys.stderr,sys.stdout.encoding,sys.stderr.encoding); '
                'import dbeaver_adapter,dbeaver_formatter,formatter; '
                'assert before==(sys.stdout,sys.stderr,sys.stdout.encoding,sys.stderr.encoding)')
        result = subprocess.run([sys.executable, '-c', code], cwd=project, env=self.env, capture_output=True)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, b'', b''))

    def test_missing_dependency_is_safe(self):
        raw = b'\xef\xbb\xbfSELECT a FROM t;\r'
        path = self.base / 'input.sql'
        path.write_bytes(raw)
        result = subprocess.run([sys.executable, '-S', str(ROOT / 'dbeaver_adapter.py'), str(path)],
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, raw)

    def test_legacy_cli_interface_unchanged(self):
        path = self.base / 'input.sql'
        for raw, code in ((b'SELECT a FROM t;', 0), (b'SELECT FROM;', 1)):
            path.write_bytes(raw)
            result = subprocess.run([sys.executable, str(ROOT / 'dbeaver_formatter.py'), str(path)],
                                    env=self.env, capture_output=True)
            self.assertEqual(result.returncode, code)
            if code:
                self.assertEqual(result.stdout, b'')
                self.assertIn(b'Formatting failed', result.stderr)
            else:
                self.assertEqual(result.stderr, b'')

    def test_log_rotation_and_safe_fields(self):
        logs = self.base / 'logs'
        logs.mkdir()
        (logs / 'adapter.jsonl').write_bytes(b'x' * 262145)
        adapter.log_event('ADAPTER-FORMAT', 'ValueError')
        self.assertTrue((logs / 'adapter.previous.jsonl').exists())
        event = json.loads((logs / 'adapter.jsonl').read_text())
        self.assertEqual(set(event), {'time', 'code', 'type', 'description'})

    def test_output_and_read_permission_failures_are_silent(self):
        path = self.base / 'input.sql'
        path.write_bytes(b'SELECT a FROM t;')
        for target in ('os.write', 'pathlib.Path.read_bytes'):
            code = ('import runpy,sys; from unittest.mock import patch; '
                    'sys.argv=[sys.argv[1],sys.argv[2]]; '
                    f'context=patch({target!r},side_effect=PermissionError("secret")); '
                    'context.start(); runpy.run_path(sys.argv[0],run_name="__main__")')
            result = subprocess.run([sys.executable, '-c', code,
                                     str(ROOT / 'dbeaver_adapter.py'), str(path)],
                                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, b'')

    def test_success_with_unexpected_print_returns_original(self):
        raw = b'\xef\xbb\xbfSELECT a FROM t;\r'
        def noisy(source, diagnostics):
            print('secret')
            return source
        with patch('formatter.format_sql', side_effect=noisy):
            self.assertEqual(adapter.format_bytes(raw), raw)
