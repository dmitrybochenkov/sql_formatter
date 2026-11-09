"""Headless local diagnosis: no SQL/output copies, no GUI, no stream diagnostics."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    # Simple fixed interface avoids argparse writing usage/errors to process streams.
    if len(sys.argv) != 4 or sys.argv[2] not in ('personal','corporate'):
        return 2
    os.environ['SQL_FORMATTER_TRACE']='1'
    os.environ['SQL_FORMATTER_LOG_DIR']=sys.argv[3]
    from formatter_modules.formatter_trace import event, stage
    try:
        with stage('read'):
            original=Path(sys.argv[1]).read_bytes()
        from dbeaver_adapter import PROFILE_FORMATTERS
        with stage('profile'):
            selected=PROFILE_FORMATTERS[sys.argv[2]]
        with stage('diagnostic_run'):
            result=selected(original)
        event('result','UNCHANGED' if result==original else 'CHANGED')
        return 0
    except Exception:
        event('diagnostic_run','ERROR')
        return 1


if __name__=='__main__':
    sys.exit(main())
