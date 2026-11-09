"""Synthetic B10.5f adapter timings; GUI acknowledgement/choice are mocked.

No user SQL or production Personal/state is read or modified. Human interaction
and real Windows Tk latency are explicitly outside these measurements.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from unittest.mock import patch
from benchmark_formatter import summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--repeats', type=int, default=3)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three repeats required')
    sys.path.insert(0, str(args.root.resolve()))
    import dbeaver_adapter as adapter
    from formatter_modules import formatter_config as config
    from formatter_modules import profile_notifications as notices
    from formatter_modules import profile_selector as selector
    raw = b'select id,name from users where active=1;'
    expected = adapter.PROFILE_FORMATTERS['corporate'](raw)
    baseline = b'schema_version=1\n# synthetic configuration\n'
    result = {'gui': 'mocked; no human latency', 'runs': {}}
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        personal = root / 'personal.toml'
        notices_seen, choices_seen = [], []
        def show(message):
            notices_seen.append(True)
            return True
        def choose(**kwargs):
            choices_seen.append(True)
            return 'corporate'
        with patch.object(config, 'personal_path', return_value=personal), \
             patch.object(config, 'user_config_directory', return_value=root), \
             patch.object(selector, 'show_profile_notice', show), \
             patch.object(selector, 'select_profile', choose), \
             patch.dict(os.environ, LOCALAPPDATA=directory, SQL_FORMATTER_LOG_DIR=str(root/'logs')):
            for mode in ('absent', 'unchanged', 'changed_identical', 'changed_different', 'invalid'):
                values = []
                personal.write_bytes(baseline)
                if mode == 'absent':
                    personal.unlink()
                notices.notify_changed(notices.read_state(), show)
                notices_seen.clear(); choices_seen.clear()
                for index in range(args.repeats):
                    if mode not in ('unchanged', 'absent'):
                        body = baseline + f'# iteration {index}\n'.encode()
                        if mode == 'changed_different':
                            body += b'[case]\nkeywords="lower"\n'
                        elif mode == 'invalid':
                            body += b'[case]\nkeywords="unsupported"\n'
                        personal.write_bytes(body)
                    start = perf_counter()
                    output = adapter.select_and_format_bytes(raw)
                    values.append(perf_counter() - start)
                    assert output == expected, mode
                result['runs'][mode] = {**summary(values), 'notices': len(notices_seen),
                                        'choices': len(choices_seen),
                                        'sha256': hashlib.sha256(expected).hexdigest()}
            values = []
            personal.write_bytes(baseline)
            for _ in range(50):
                start = perf_counter(); notices.read_state(); values.append(perf_counter()-start)
            result['configuration_only'] = summary(values)
    args.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
