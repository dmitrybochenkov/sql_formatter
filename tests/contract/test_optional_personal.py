"""Headless local configuration contracts; no access to real user settings."""
import contextlib
import io
import json
import os
from pathlib import Path, PureWindowsPath
import tempfile
import unittest
from unittest.mock import Mock, patch

import dbeaver_adapter as adapter
from formatter_modules import formatter_config as config, profile_notifications as notices
from formatter_modules.corporate_profile import CORPORATE


class OptionalPersonalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / 'user' / 'SQLFormatter'
        for mocked in (patch.object(config, 'user_config_directory', return_value=self.directory),
                       patch.dict(os.environ, SQL_FORMATTER_LOG_DIR=str(self.root / 'logs'))):
            mocked.start()
            self.addCleanup(mocked.stop)

    def write(self, text):
        self.directory.mkdir(parents=True, exist_ok=True)
        config.personal_path().write_text(text, encoding='utf-8')

    def test_absence_never_creates_files_or_opens_gui(self):
        raw = b'\xef\xbb\xbfselect A from T;\r\n'
        expected = adapter.PROFILE_FORMATTERS['corporate'](raw)
        with patch('formatter_modules.profile_selector.show_profile_notice') as show, \
             patch('formatter_modules.profile_selector.select_profile') as choose:
            for _ in range(2):
                self.assertEqual(adapter.select_and_format_bytes(raw), expected)
                self.assertEqual(adapter.PROFILE_FORMATTERS['personal'](raw), expected)
            show.assert_not_called()
            choose.assert_not_called()
        self.assertFalse(self.directory.exists())

    def test_all_state_transitions_and_reappearance(self):
        show = Mock(return_value=True)
        choices = Mock(return_value='corporate')
        raw = b'SELECT a FROM t;'
        expected = adapter.PROFILE_FORMATTERS['corporate'](raw)
        # Every state is invoked twice: unchanged state must not repeat notice.
        states = [(None, 0, 0), ('schema_version=1', 0, 0),
                  ('schema_version=1\n[case]\nkeywords="lower"', 1, 2),
                  ('schema_version=1\n[case]\nkeywords="preserve"', 2, 4),
                  ('invalid confidential TOML', 3, 4), ('schema_version=1', 4, 4),
                  (None, 4, 4), ('schema_version=1', 4, 4)]
        with patch('formatter_modules.profile_selector.show_profile_notice', show), \
             patch('formatter_modules.profile_selector.select_profile', choices):
            for body, count, selected in states:
                if body is None:
                    config.personal_path().unlink(missing_ok=True)
                else:
                    self.write(body)
                for _ in range(2):
                    self.assertEqual(adapter.select_and_format_bytes(raw), expected)
                self.assertEqual(show.call_count, count)
                self.assertEqual(choices.call_count, selected)
        self.assertNotIn('confidential', str(show.call_args_list))
        saved = notices.state_path().read_text()
        self.assertNotIn(str(self.root), saved)
        self.assertNotIn('keywords', saved)

    def test_two_user_directories_are_independent(self):
        show = Mock(return_value=True)
        self.write('schema_version=1\n[case]\nkeywords="lower"')
        first = config.load_personal()
        notices.notify_changed(notices.read_state(), show)
        second_dir = self.root / 'second' / 'SQLFormatter'
        with patch.object(config, 'user_config_directory', return_value=second_dir):
            self.assertIsNone(config.load_personal())
            notices.notify_changed(notices.read_state(), show)
            self.assertFalse(second_dir.exists())
            second_dir.mkdir(parents=True)
            config.personal_path().write_text('schema_version=1\n[case]\nkeywords="preserve"')
            second = config.load_personal()
            notices.notify_changed(notices.read_state(), show)
        self.assertNotEqual(first, second)
        self.assertEqual(config.load_personal(), first)
        notices.notify_changed(notices.read_state(), show)
        self.assertEqual(show.call_count, 2)
        self.assertTrue((second_dir / 'profile_state.json').exists())

    def test_project_template_unc_and_cwd_never_supply_personal(self):
        fake_project = self.root / 'shared'
        fake_project.mkdir()
        (fake_project / 'personal.toml').write_text('bad')
        (fake_project / 'config_templates').mkdir()
        (fake_project / 'config_templates' / 'personal.example.toml').write_text('bad')
        original_read = Path.read_bytes
        seen = []
        def read(path):
            seen.append(path)
            return original_read(path)
        previous = Path.cwd()
        try:
            os.chdir(fake_project)
            with patch.object(config, '__file__', r'\\server\share\formatter_modules\formatter_config.py'), \
                 patch.object(Path, 'read_bytes', read):
                self.assertFalse(notices.read_state().present)
                self.assertIsNone(config.load_personal())
            self.assertEqual(seen, [self.directory / 'personal.toml'] * 2)
        finally:
            os.chdir(previous)

    def test_invalid_keys_and_values_are_not_exposed(self):
        for body in ('schema_version=1\n[private_object_name]\nsecret="value"',
                     'schema_version=1\n[case]\nprivate_object_name="value"'):
            self.write(body)
            state = notices.read_state()
            self.assertIsNotNone(state.error)
            self.assertNotIn('private_object_name', state.message)
            self.assertNotIn('value', state.message)

    def test_unreadable_is_error_but_missing_is_normal(self):
        with patch.object(Path, 'read_bytes', side_effect=PermissionError('sensitive path')):
            state = notices.read_state()
        self.assertTrue(state.present)
        self.assertIsNotNone(state.error)
        self.assertNotIn('sensitive', state.message)
        self.assertFalse(notices.read_state().present)

    def test_corporate_strict_validation_and_repeat(self):
        from formatter import validate_sql_unchanged
        raw = b"select A, 'SQL, TEXT' as S from T where A=1 and B=2;\r\n"
        expected = adapter.PROFILE_FORMATTERS['corporate'](raw)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            actual = adapter.select_and_format_bytes(raw)
            repeated = adapter.select_and_format_bytes(actual)
        self.assertEqual(actual, expected)
        self.assertEqual(repeated, actual)
        self.assertEqual(out.getvalue() + err.getvalue(), '')
        validate_sql_unchanged(raw.decode(), actual.decode())


class PlatformPersonalPathTests(unittest.TestCase):
    def test_windows_absolute_local_directory_and_path_semantics(self):
        with patch.object(config.sys, 'platform', 'win32'), \
             patch.dict(os.environ, LOCALAPPDATA=r'C:\Users\Имя пользователя\AppData\Local'):
            self.assertEqual(PureWindowsPath(str(config.personal_path())),
                             PureWindowsPath(r'C:\Users\Имя пользователя\AppData\Local\SQLFormatter\personal.toml'))
            self.assertEqual(PureWindowsPath(str(notices.state_path())).parent,
                             PureWindowsPath(str(config.personal_path())).parent)

    def test_windows_missing_or_relative_localappdata_has_no_fallback(self):
        with patch.object(config.sys, 'platform', 'win32'), patch.dict(os.environ, {}, clear=True), \
             patch.object(Path, 'home', side_effect=AssertionError('home fallback')), \
             patch.object(Path, 'read_bytes', side_effect=AssertionError('file discovery')):
            for value in ('', 'relative', r'C:relative', r'\relative'):
                os.environ['LOCALAPPDATA'] = value
                self.assertIsNone(config.personal_path())
                self.assertIsNone(notices.state_path())
                self.assertIsNone(config.load_personal())
                self.assertFalse(notices.read_state().present)
                show = Mock()
                notices.notify_changed(notices.read_state(), show)
                show.assert_not_called()

    def test_macos_and_linux_deterministic_paths_without_localappdata(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(Path, 'home', return_value=Path('/users/example')):
            with patch.object(config.sys, 'platform', 'darwin'):
                self.assertEqual(config.personal_path(), Path('/users/example/Library/Application Support/SQLFormatter/personal.toml'))
            with patch.object(config.sys, 'platform', 'linux'):
                self.assertEqual(config.personal_path(), Path('/users/example/.config/SQLFormatter/personal.toml'))
                os.environ['XDG_CONFIG_HOME'] = '/custom/config'
                self.assertEqual(config.personal_path(), Path('/custom/config/SQLFormatter/personal.toml'))
                os.environ['XDG_CONFIG_HOME'] = 'relative'
                self.assertEqual(config.personal_path(), Path('/users/example/.config/SQLFormatter/personal.toml'))
