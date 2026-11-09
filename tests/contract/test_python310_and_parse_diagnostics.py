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

from formatter_modules import formatter_config as config
from formatter_modules.corporate_profile import CORPORATE
from dbeaver_adapter import format_bytes

ROOT = Path(__file__).resolve().parents[2]


class CompatibilityAndDiagnosticsTests(unittest.TestCase):
    def test_python_version_toml_loader_and_defaults(self):
        self.assertGreaterEqual(sys.version_info, (3, 10))
        self.assertEqual(config.tomllib.__name__, 'tomli' if sys.version_info < (3, 11) else 'tomllib')
        self.assertEqual(config.parse_personal(b'schema_version=1'), CORPORATE)
        self.assertEqual(config.parse_personal(b'schema_version=1').get('profile_selector', 'timeout_seconds'), 3)

    def test_timeout_validation_and_style_independence(self):
        for timeout in (1, 3, 60):
            settings = config.validate({'schema_version': 1, 'profile_selector': {'timeout_seconds': timeout}})
            self.assertEqual(settings.get('profile_selector', 'timeout_seconds'), timeout)
            self.assertEqual(config.differences(settings, CORPORATE), ())
            self.assertEqual(settings.fingerprint, CORPORATE.fingerprint)
        for timeout in (True, False, 0, -1, 61, 3.5, '3', None, []):
            with self.subTest(timeout=timeout), self.assertRaises(config.ConfigurationError):
                config.validate({'schema_version': 1, 'profile_selector': {'timeout_seconds': timeout}})
        for selector in ([], {'unknown': 3}):
            with self.assertRaises(config.ConfigurationError):
                config.validate({'schema_version': 1, 'profile_selector': selector})

    def test_help_does_not_read_file_or_open_gui(self):
        with tempfile.TemporaryDirectory() as directory:
            for option in ('-h', '--help'):
                run = subprocess.run([sys.executable, '-B', str(ROOT/'formatter.py'), option],
                                     cwd=directory, capture_output=True, timeout=30)
                self.assertEqual(run.returncode, 0)
                self.assertEqual(run.stderr, b'')
                self.assertIn(b'Usage: formatter.py [SQL_FILE]', run.stdout)

    def test_parse_position_opt_in_without_payload(self):
        source = 'select id\r\nfrom sensitive_object_zz\r\nwhere id = :;'
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                SQL_FORMATTER_TRACE='0', SQL_FORMATTER_LOG_DIR=directory):
            raw = b'\xef\xbb\xbf' + source.encode()
            self.assertEqual(format_bytes(raw), raw)
            path = Path(directory)/'diagnostic.jsonl'
            self.assertFalse(path.exists())
            out, err = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, SQL_FORMATTER_TRACE='1'), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(format_bytes(raw), raw)
            self.assertEqual(out.getvalue()+err.getvalue(), '')
            text = path.read_text()
            self.assertNotIn('sensitive_object_zz', text)
            self.assertNotIn(source, text)
            self.assertNotIn(directory, text)
            records = [json.loads(row) for row in text.splitlines()]
            failure = next(r for r in records if r['code'] == 'UNPARSABLE')
            self.assertEqual(failure['stage'], 'parse')
            self.assertEqual(failure['segment'], 'unparsable')
            self.assertEqual((failure['line'], failure['column']), (3, 10))
            self.assertEqual(failure['error_type'], 'SQLParseError')

    def test_template_documents_actual_corporate_values(self):
        template = (ROOT/'config_templates/personal.example.toml').read_text()
        self.assertEqual(config.parse_personal(template.encode()), CORPORATE)
        section = None
        previous = ''
        for line in template.splitlines():
            if line.startswith('['):
                section = line.strip('[]')
            if '=' in line and not line.startswith('#'):
                key = line.split('=', 1)[0].strip()
                self.assertTrue(previous.startswith('# Corporate: '), key)
                documented = json.loads(previous.removeprefix('# Corporate: ').split(' (служебный')[0])
                actual = 1 if key == 'schema_version' else CORPORATE.get(section, key)
                if isinstance(actual, tuple):
                    self.assertEqual(sorted(documented), sorted(actual))
                else:
                    self.assertEqual(documented, actual)
            previous = line

    def test_timeout_only_setting_does_not_open_any_window(self):
        from dbeaver_adapter import select_and_format_bytes
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'user_config_directory', return_value=Path(directory)):
            config.personal_path().write_text('schema_version=1\n[profile_selector]\ntimeout_seconds=1')
            with patch('formatter_modules.profile_selector.select_profile') as choose, \
                 patch('formatter_modules.profile_selector.show_profile_notice') as show:
                raw = b'select id from events;'
                self.assertEqual(select_and_format_bytes(raw), format_bytes(raw))
                choose.assert_not_called()
                show.assert_not_called()

    def test_adapter_auto_personal_once_without_separate_alert(self):
        import dbeaver_adapter as adapter
        from tests.unit.test_profile_selector import FakeTk
        fake = FakeTk('timeout')
        with tempfile.TemporaryDirectory() as directory, patch.object(config, 'user_config_directory', return_value=Path(directory)):
            config.personal_path().write_text('schema_version=1\n[case]\nkeywords="lower"\n[profile_selector]\ntimeout_seconds=1')
            with patch.dict(sys.modules, tkinter=fake), \
                 patch('formatter_modules.profile_selector.monotonic', side_effect=lambda: fake.now), \
                 patch('formatter_modules.profile_selector.show_profile_notice') as notice, \
                 patch.object(adapter, 'format_bytes', wraps=adapter.format_bytes) as engine:
                result = adapter.select_and_format_bytes(b'SELECT id FROM events;')
                self.assertTrue(result.startswith(b'select\n'))
                engine.assert_called_once()
                notice.assert_not_called()
                self.assertIn('Автоматически: Personal через 1 с', fake.labels)
                self.assertFalse((Path(directory)/'profile_state.json').exists())
