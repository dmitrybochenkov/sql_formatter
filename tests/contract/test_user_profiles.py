import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, Mock
from concurrent.futures import ThreadPoolExecutor

import dbeaver_adapter as adapter
from formatter_modules import formatter_config as c, profile_notifications as n
from formatter_modules.corporate_profile import CORPORATE


class ProfileNotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.path=self.root/'personal.toml';self.path.write_bytes((Path(__file__).resolve().parents[2]/'config_templates'/'personal.example.toml').read_bytes())
        for p in (patch.object(c,'personal_path',return_value=self.path),
                  patch.object(c,'user_config_directory',return_value=self.root),
                  patch('formatter_modules.profile_selector.show_profile_notice', return_value=True),
                  patch.dict(os.environ,LOCALAPPDATA=str(self.root),SQL_FORMATTER_LOG_DIR=str(self.root/'logs'))):
            p.start();self.addCleanup(p.stop)

    def test_first_shipped_no_notice_or_state(self):
        show=Mock()
        n.notify_changed(n.read_state(),show)
        show.assert_not_called();self.assertTrue(n.state_path().exists())

    def test_change_repeat_error_fix_and_return_to_shipped(self):
        shipped=self.path.read_bytes();show=Mock(return_value=True)
        for raw in (b'schema_version=1\n[case]\nkeywords="lower"',b'schema_version=1\n[case]\nkeywords="wrong"',b'schema_version=1',shipped):
            self.path.write_bytes(raw)
            state=n.read_state();before=show.call_count
            n.notify_changed(state,show);n.notify_changed(state,show)
            self.assertEqual(show.call_count,before+1)
        saved=n.state_path().read_text()
        self.assertNotIn('keywords',saved);self.assertNotIn('wrong',saved)
        self.assertEqual(set(json.loads(saved)),{'version','installations'})

    def test_gui_failure_does_not_record_delivery(self):
        self.path.write_bytes(b'schema_version=1\n[case]\nkeywords="lower"')
        with self.assertRaises(RuntimeError):n.notify_changed(n.read_state(),Mock(side_effect=RuntimeError()))
        self.assertFalse(n.state_path().exists())
        n.notify_changed(n.read_state(),Mock(return_value=False));self.assertFalse(n.state_path().exists())

    def test_parallel_notice_and_atomic_valid_state(self):
        self.path.write_bytes(b'schema_version=1\n[case]\nkeywords="lower"')
        show=Mock(return_value=True);state=n.read_state()
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda _: n.notify_changed(state,show),range(12)))
        self.assertEqual(show.call_count,1)
        self.assertEqual(len(json.loads(n.state_path().read_text())['installations']),1)

    def test_installations_and_corporate_update(self):
        self.path.write_bytes(b'schema_version=1\n[case]\nkeywords="lower"');show=Mock(return_value=True)
        n.notify_changed(n.read_state(),show)
        other=self.root/'other.toml';other.write_bytes(self.path.read_bytes())
        with patch.object(c,'personal_path',return_value=other):n.notify_changed(n.read_state(),show)
        self.assertEqual(show.call_count,2)
        updated=c.validate({'schema_version':1,'case':{'keywords':'lower'}})
        with patch.object(n,'CORPORATE',updated):n.notify_changed(n.read_state(),show)
        self.assertEqual(show.call_count,3)

    def test_missing_corrupt_and_unwritable_state(self):
        self.path.write_bytes(b'bad');state=n.read_state();self.assertIsNotNone(state.error)
        show=Mock(return_value=True)
        with patch.object(n,'state_path',return_value=None):n.notify_changed(state,show)
        self.assertEqual(show.call_count,1)
        with patch.object(Path,'mkdir',side_effect=PermissionError()):n.notify_changed(state,show)
        self.assertEqual(show.call_count,2)
        n.state_path().parent.mkdir(parents=True,exist_ok=True);n.state_path().write_text('broken')
        n.notify_changed(state,show)
        self.assertEqual(show.call_count,3)

    def test_adapter_three_states_and_reload(self):
        raw=b'select A from T;';expected=adapter.format_bytes(raw)
        with patch('formatter_modules.profile_selector.show_profile_notice',return_value=True) as notice,patch('formatter_modules.profile_selector.select_profile',return_value='personal') as choose:
            self.assertEqual(adapter.select_and_format_bytes(raw),expected);choose.assert_not_called();notice.assert_not_called()
            self.path.write_text('schema_version=1\n[case]\nkeywords="lower"')
            personal=adapter.select_and_format_bytes(raw)
            self.assertTrue(personal.startswith(b'select\n'));choose.assert_called_once()
            self.assertEqual(adapter.select_and_format_bytes(raw),personal);self.assertEqual(notice.call_count,1)
            self.path.write_text('schema_version=1\n[case]\nkeywords="wrong"');choose.reset_mock()
            self.assertEqual(adapter.select_and_format_bytes(raw),expected);choose.assert_not_called()
            self.assertEqual(notice.call_count,2)

    def test_cancel_gui_error_noisy_notice_and_invalid_headless(self):
        raw=b'\xef\xbb\xbfselect A from T;\r\n'
        self.path.write_text('schema_version=1\n[case]\nkeywords="lower"')
        for action in (lambda:None,lambda:(_ for _ in ()).throw(RuntimeError())):
            with patch('formatter_modules.profile_selector.show_profile_notice',return_value=True),patch('formatter_modules.profile_selector.select_profile',side_effect=action):
                self.assertEqual(adapter.select_and_format_bytes(raw),raw)
        def noisy(message):print('not SQL');return True
        with patch('formatter_modules.profile_selector.show_profile_notice',side_effect=noisy),patch('formatter_modules.profile_selector.select_profile',return_value='personal'):
            self.path.write_text('schema_version=1\n[case]\nkeywords="preserve"')
            out,err=io.StringIO(),io.StringIO()
            with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):self.assertEqual(adapter.select_and_format_bytes(raw),raw)
            self.assertEqual(out.getvalue()+err.getvalue(),'')
        self.path.write_text('bad')
        with patch('formatter_modules.profile_selector.show_profile_notice',side_effect=ImportError()),patch('formatter_modules.profile_selector.select_profile') as choose:
            self.assertEqual(adapter.select_and_format_bytes(raw),adapter.format_bytes(raw));choose.assert_not_called()

    def test_corporate_never_reads_personal(self):
        with patch.object(c,'load_personal',side_effect=AssertionError()):
            self.assertEqual(adapter.PROFILE_FORMATTERS['corporate'](b'SELECT a FROM t;'),adapter.format_bytes(b'SELECT a FROM t;'))

    def test_selected_snapshot_survives_edit_during_dialog(self):
        self.path.write_text('schema_version=1\n[case]\nkeywords="lower"')
        def select():
            self.path.write_text('schema_version=1\n[case]\nkeywords="upper"')
            return 'personal'
        with patch('formatter_modules.profile_selector.select_profile',side_effect=select),patch('formatter_modules.profile_selector.show_profile_notice',return_value=True):
            self.assertTrue(adapter.select_and_format_bytes(b'SELECT a FROM t;').startswith(b'select\n'))
        self.assertTrue(adapter.select_and_format_bytes(b'SELECT a FROM t;').startswith(b'SELECT\n'))

    def test_profile_routes_do_not_inherit_another_profile(self):
        self.path.write_text('schema_version=1\n[case]\nkeywords="lower"')
        with c.use_settings(CORPORATE):
            self.assertTrue(adapter.PROFILE_FORMATTERS['personal'](b'SELECT a FROM t;').startswith(b'select\n'))
        with c.use_settings(c.load_personal()):
            self.assertTrue(adapter.PROFILE_FORMATTERS['corporate'](b'SELECT a FROM t;').startswith(b'SELECT\n'))

    def test_parallel_processes_deliver_only_one_notice(self):
        import subprocess
        import sys
        self.path.write_text('schema_version=1\n[case]\nkeywords="lower"')
        delivered=self.root/'delivered'
        code='''import sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from formatter_modules import formatter_config as c, profile_notifications as n
c.personal_path=lambda: Path(sys.argv[2])
c.user_config_directory=lambda: Path(sys.argv[2]).parent
def show(message):
    with Path(sys.argv[3]).open('a') as stream: stream.write('1')
    time.sleep(0.1)
    return True
n.notify_changed(n.read_state(),show)
'''
        root=Path(__file__).resolve().parents[2]
        children=[subprocess.Popen([sys.executable,'-B','-c',code,str(root),str(self.path),str(delivered)],
                                   stdout=subprocess.PIPE,stderr=subprocess.PIPE) for _ in range(4)]
        try:
            for child in children:
                output,error=child.communicate(timeout=15)
                self.assertEqual((child.returncode,output,error),(0,b'',b''))
        finally:
            for child in children:
                if child.poll() is None:child.kill();child.wait()
        self.assertEqual(delivered.read_text(),'1')
        self.assertEqual(len(json.loads(n.state_path().read_text())['installations']),1)
