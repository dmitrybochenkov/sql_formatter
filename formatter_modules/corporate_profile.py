"""Built-in release policy. Never reads Personal or user overrides."""
from formatter_modules.formatter_config import validate

CORPORATE = validate({
    'schema_version': 1,
    'case': {'keywords': 'upper', 'functions': 'upper', 'identifiers': 'lower',
             'types': 'upper', 'literals': 'upper'},
    'commas': {'select': 'leading', 'from': 'leading', 'group_by': 'leading', 'order_by': 'leading'},
    'spacing': {'blank_line_before': ['join', 'where', 'group_by', 'having', 'qualify', 'order_by']},
    'where': {'insert_1_equals_1': True}, 'group_by': {'layout': 'multiline'},
})
