"""Subprocess fixture: exercise the real adapter with a headless UI boundary."""
import sys


def adapter_command(script, path, profile='personal', python_options=(), interactive=False):
    comparison = (
        'import formatter_modules.profile_notifications as n; '
        'from formatter_modules.corporate_profile import CORPORATE; '
        'n.read_state=lambda: n.PersonalState(CORPORATE,"test",("case.keywords",),None); '
        'n.notify_changed=lambda *a: None; '
    ) if interactive else ''
    code = (
        'import sys,runpy; from pathlib import Path; '
        'script,path,profile=sys.argv[1:]; '
        'sys.path.insert(0,str(Path(script).parent)); '
        'import formatter_modules.profile_selector as selector; '
        'selector.show_profile_notice=lambda message: True; '
        'selector.select_profile=lambda **kwargs: None if profile=="cancel" else profile; ' + comparison +
        'sys.argv=[script,path]; runpy.run_path(script,run_name="__main__")'
    )
    return [sys.executable, *python_options, '-c', code, str(script), str(path), profile]
