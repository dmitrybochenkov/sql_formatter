import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import dbeaver_adapter as adapter
from tests.adapter_runner import adapter_command

ROOT = Path(__file__).resolve().parents[2]


class B9AdapterTests(unittest.TestCase):
    RAW = b'\xef\xbb\xbfselect A from T;\r\n'
    EXPECTED = b'SELECT\n    a\nFROM t\n;\n'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', SQL_FORMATTER_LOG_DIR=str(self.base/'logs'))
        self.env_patch = patch.dict(os.environ, self.env)
        self.env_patch.start()
        self.addCleanup(self.env_patch.stop)

    def test_both_profile_routes_are_explicit(self):
        for profile in ('personal', 'corporate'):
            selected = Mock(return_value=self.EXPECTED)
            other = Mock(side_effect=AssertionError('wrong route'))
            routes = dict.fromkeys(('personal','corporate'), other)
            routes[profile] = selected
            with patch('dbeaver_profile_selector.select_profile', return_value=profile), \
                 patch.dict(adapter.PROFILE_FORMATTERS, routes):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.EXPECTED)
                selected.assert_called_once_with(self.RAW)
                other.assert_not_called()

    def test_profiles_match_b8_and_are_idempotent(self):
        self.assertIs(adapter.PROFILE_FORMATTERS['personal'], adapter.PROFILE_FORMATTERS['corporate'])
        for profile in adapter.PROFILE_FORMATTERS:
            with patch('dbeaver_profile_selector.select_profile', return_value=profile):
                first = adapter.select_and_format_bytes(self.RAW)
                self.assertEqual(first, self.EXPECTED)
                self.assertEqual(first, adapter.format_bytes(self.RAW))
                self.assertEqual(adapter.select_and_format_bytes(first), first)

    def test_cancel_and_unknown_profile_never_format(self):
        for choice in (None, 'unknown'):
            formatter = Mock(side_effect=AssertionError('must not format'))
            with patch('dbeaver_profile_selector.select_profile', return_value=choice), \
                 patch.dict(adapter.PROFILE_FORMATTERS, personal=formatter, corporate=formatter):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.RAW)
                formatter.assert_not_called()

    def test_gui_errors_and_noisy_gui_return_original(self):
        def noisy():
            print('secret', file=sys.stdout)
            print('secret', file=sys.stderr)
            return 'personal'
        for action in (RuntimeError('secret'), ImportError('secret'), KeyboardInterrupt(), noisy):
            out, err = io.StringIO(), io.StringIO()
            with patch('dbeaver_profile_selector.select_profile', side_effect=action), \
                 contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.RAW)
            self.assertEqual(out.getvalue()+err.getvalue(), '')
        self.assertNotIn('secret', (self.base/'logs/adapter.jsonl').read_text())

    def test_format_failure_and_e004_preserve_bytes(self):
        with patch('dbeaver_profile_selector.select_profile', return_value='corporate'):
            with patch('formatter.format_sql', side_effect=RuntimeError('secret')):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.RAW)
            for raw in (b'\xef\xbb\xbfSELECT FROM;\r', b'\xef\xbb\xbfselect SUM(A) over W from T;\r\n'):
                self.assertEqual(adapter.select_and_format_bytes(raw), raw)
            with patch.dict(adapter.PROFILE_FORMATTERS, corporate=Mock(side_effect=RuntimeError('secret'))):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.RAW)
            with patch.dict(adapter.PROFILE_FORMATTERS, corporate=Mock(return_value=None)):
                self.assertEqual(adapter.select_and_format_bytes(self.RAW), self.RAW)

    def test_merged_subprocess_transport_and_sequential_calls(self):
        path = self.base/'SQL с пробелом.sql'
        for profile, expected in [('personal',self.EXPECTED), ('corporate',self.EXPECTED), ('cancel',self.RAW)]:
            path.write_bytes(self.RAW)
            for _ in range(2):
                result = subprocess.run(adapter_command(ROOT/'dbeaver_adapter.py',path,profile),
                                        env=self.env, cwd=self.base, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=30)
                self.assertEqual(result.returncode,0)
                self.assertEqual(result.stdout,expected)
                self.assertEqual(path.read_bytes(),self.RAW)

    def test_cli_and_imports_do_not_load_tk(self):
        path = self.base/'input.sql'; path.write_bytes(self.RAW)
        for script in ('formatter.py','dbeaver_formatter.py'):
            code = ('import sys,runpy; from pathlib import Path; '
                    'sys.path.insert(0,str(Path(sys.argv[1]).parent)); '
                    'sys.modules["tkinter"]=None; sys.modules["dbeaver_profile_selector"]=None; '
                    'sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")')
            result = subprocess.run([sys.executable,'-c',code,str(ROOT/script),str(path)],env=self.env,capture_output=True)
            self.assertEqual((result.returncode,result.stdout,result.stderr),(0,self.EXPECTED,b''))
        code = 'import sys; import dbeaver_adapter,dbeaver_profile_selector; assert "tkinter" not in sys.modules'
        result = subprocess.run([sys.executable,'-c',code],cwd=ROOT,env=self.env,capture_output=True)
        self.assertEqual((result.returncode,result.stdout,result.stderr),(0,b'',b''))

    def test_gui_failure_in_merged_subprocess(self):
        path = self.base/'input.sql'; path.write_bytes(self.RAW)
        for action in ('sys.modules["tkinter"]=None',
                       'selector.select_profile=lambda: (_ for _ in ()).throw(RuntimeError("secret"))',
                       'selector.select_profile=lambda: print("secret") or "personal"'):
            code = ('import sys,runpy; from pathlib import Path; '
                    'sys.path.insert(0,str(Path(sys.argv[1]).parent)); '
                    'import dbeaver_profile_selector as selector; ' + action + '; '
                    'sys.argv=sys.argv[1:]; runpy.run_path(sys.argv[0],run_name="__main__")')
            result = subprocess.run([sys.executable,'-c',code,str(ROOT/'dbeaver_adapter.py'),str(path)],
                                    env=self.env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
            self.assertEqual((result.returncode,result.stdout),(0,self.RAW))

    def test_cancel_with_unwritable_log(self):
        with patch('dbeaver_profile_selector.select_profile', return_value=None), \
             patch.object(Path,'mkdir',side_effect=PermissionError()):
            self.assertEqual(adapter.select_and_format_bytes(self.RAW),self.RAW)
