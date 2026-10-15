"""Subprocess fixture: exercise the real adapter with a headless UI boundary."""
import sys


def adapter_command(script, path, profile='personal', python_options=()):
    code = (
        'import sys,runpy; from pathlib import Path; '
        'script,path,profile=sys.argv[1:]; '
        'sys.path.insert(0,str(Path(script).parent)); '
        'import dbeaver_profile_selector as selector; '
        'selector.select_profile=lambda: None if profile=="cancel" else profile; '
        'sys.argv=[script,path]; runpy.run_path(script,run_name="__main__")'
    )
    return [sys.executable, *python_options, '-c', code, str(script), str(path), profile]
