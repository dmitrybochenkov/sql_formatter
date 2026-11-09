"""Programmatic SQLFluff 4.4.0 configuration; no cwd/home/project discovery."""
from sqlfluff.core import FluffConfig
from formatter_modules.formatter_config import current_settings

RULE_SETTINGS = {'CP01': ('keywords', 'capitalisation_policy'),
                 'CP02': ('identifiers', 'extended_capitalisation_policy'),
                 'CP03': ('functions', 'extended_capitalisation_policy'),
                 'CP04': ('literals', 'capitalisation_policy'),
                 'CP05': ('types', 'extended_capitalisation_policy')}


def active_rules():
    return tuple(code for code, (name, _) in RULE_SETTINGS.items()
                 if current_settings().get('case', name) != 'preserve')


def build_config(case=False):
    settings = current_settings()
    rules = {}
    for code, (name, policy) in RULE_SETTINGS.items():
        value = settings.get('case', name)
        rules['capitalisation.' + name] = {policy: value if value != 'preserve' else 'consistent'}
    rules['capitalisation.identifiers']['unquoted_identifiers_policy'] = 'all'
    rules['layout.commas'] = {'line_position': 'leading', 'spacing_after': 'single'}
    return FluffConfig(configs={
        'core': {'dialect': 'teradata', 'templater': 'raw', 'max_line_length': 120,
                 'exclude_rules': '' if case else 'AL01,ST05',
                 **({'rules': ','.join(active_rules()), 'disable_noqa': True} if case else {})},
        'indentation': {'indent_unit': 'space', 'tab_space_size': 4}, 'rules': rules,
    })
