"""Byte transport tests, not a claim of real Windows or DBeaver acceptance."""
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch
import pytest
from dbeaver_adapter import select_and_format_bytes
from formatter_modules import formatter_config as config
from tests.regression.test_parenthesized_lists import settings

ROOT=Path(__file__).resolve().parents[2]


def run(script, path, tmp_path, **env):
    environment={**os.environ,'LOCALAPPDATA':str(tmp_path),'XDG_CONFIG_HOME':str(tmp_path),
                 'SQL_FORMATTER_LOG_DIR':str(tmp_path/'logs'),'PYTHONIOENCODING':'cp1251',**env}
    return subprocess.run([sys.executable,str(ROOT/script),str(path)],cwd=tmp_path,env=environment,
                          stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)


def test_cli_traceback_is_utf8_with_legacy_stream_encoding(tmp_path):
    path=tmp_path/'Запрос ошибка.sql'; original=b'SELECT FROM ;';path.write_bytes(original)
    result=run('formatter.py',path,tmp_path)
    assert result.returncode!=0 and result.stdout==b''
    assert 'Обнаружен нераспознанный SQL' in result.stderr.decode('utf-8')
    assert path.read_bytes()==original


@pytest.mark.parametrize('ending',['\n','\r\n','\r'])
def test_adapter_unicode_bytes_and_no_diagnostics(tmp_path,ending):
    path=tmp_path/'Запрос с пробелом.sql'
    raw=("select a AS Количество from t /* русский"+ending+"текст */;").encode()
    path.write_bytes(raw)
    result=run('dbeaver_adapter.py',path,tmp_path)
    assert result.returncode==0 and result.stderr==b''
    assert 'Количество' in result.stdout.decode('utf-8')
    assert ('/* русский'+ending+'текст */').encode() in result.stdout
    assert path.read_bytes()==raw
    path.write_bytes(result.stdout)
    assert run('dbeaver_adapter.py',path,tmp_path).stdout==result.stdout


@pytest.mark.parametrize('raw',[b'\xef\xbb\xbfSELECT FROM ;\r\n',b'\xff\xfeinvalid',b'SELECT ROW_NUMBER() OVER win FROM t;'])
def test_adapter_failure_merged_stream_is_original(tmp_path,raw):
    path=tmp_path/'input.sql';path.write_bytes(raw)
    result=run('dbeaver_adapter.py',path,tmp_path)
    assert result.stdout+result.stderr==raw
    assert path.read_bytes()==raw


def test_cancel_and_personal_snapshot(tmp_path):
    with patch.object(config,'user_config_directory',return_value=tmp_path):
        (tmp_path/'personal.toml').write_text('schema_version=1\n[layout.parenthesized_lists]\nmode="multiline"\n')
        raw=b'SELECT a FROM t WHERE a IN (1,2);'
        with patch('formatter_modules.profile_selector.select_profile',return_value=None):
            assert select_and_format_bytes(raw)==raw
        with patch('formatter_modules.profile_selector.select_profile',return_value='personal'):
            actual=select_and_format_bytes(raw)
            assert b'IN (\n    1\n    , 2\n)' in actual
            assert select_and_format_bytes(actual)==actual
        with patch('formatter_modules.profile_selector.select_profile',return_value='corporate'):
            assert b'IN (1,2)' in select_and_format_bytes(raw)
