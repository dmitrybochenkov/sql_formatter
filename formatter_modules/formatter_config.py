"""Strict, immutable user styles. No SQLFluff/file discovery or GUI here."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import tomllib
import os
import sys
from pathlib import PureWindowsPath

def user_config_directory():
    """One platform user location; never discover configuration near the code."""
    if sys.platform == 'win32':
        local = os.environ.get('LOCALAPPDATA', '')
        # A relative/drive-relative value must not turn into cwd discovery.
        if not local or not PureWindowsPath(local).is_absolute():
            return None
        return Path(local) / 'SQLFormatter'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Application Support' / 'SQLFormatter'
    local = os.environ.get('XDG_CONFIG_HOME', '')
    base = Path(local) if local and Path(local).is_absolute() else Path.home() / '.config'
    return base / 'SQLFormatter'


def personal_path():
    directory = user_config_directory()
    return directory / 'personal.toml' if directory is not None else None

# Versioned Personal defaults, deliberately independent of Corporate.
PERSONAL_DEFAULTS = {
    'case': {'keywords': 'upper', 'functions': 'upper', 'identifiers': 'lower',
             'types': 'upper', 'literals': 'upper'},
    'commas': {'select': 'leading', 'from': 'leading', 'group_by': 'leading', 'order_by': 'leading'},
    'spacing': {'blank_line_before': ['join', 'where', 'group_by', 'having', 'qualify', 'order_by']},
    'where': {'insert_1_equals_1': True}, 'group_by': {'layout': 'multiline'},
}
CLAUSES = frozenset(('from', 'join', 'where', 'group_by', 'having', 'qualify', 'order_by'))


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    values: tuple

    def get(self, section, key):
        return dict(dict(self.values)[section])[key]

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(self.values, ensure_ascii=True).encode()).hexdigest()


def validate(data):
    if not isinstance(data, dict):
        raise ConfigurationError('Personal: требуется таблица TOML')
    if type(data.get('schema_version')) is not int or data['schema_version'] != 1:
        raise ConfigurationError('schema_version: требуется целое число 1')
    unknown = set(data) - set(PERSONAL_DEFAULTS) - {'schema_version'}
    if unknown:
        raise ConfigurationError('Personal: неизвестный раздел')
    result = []
    for section, defaults in PERSONAL_DEFAULTS.items():
        supplied = data.get(section, {})
        if not isinstance(supplied, dict):
            raise ConfigurationError(f'[{section}]: требуется таблица')
        unknown = set(supplied) - set(defaults)
        if unknown:
            raise ConfigurationError(f'[{section}]: неизвестный параметр')
        values = []
        for key, default in defaults.items():
            value = supplied.get(key, default)
            name = f'[{section}] {key}'
            if section == 'spacing':
                if (type(value) is not list or any(type(v) is not str for v in value)
                        or len(set(value)) != len(value) or not set(value) <= CLAUSES):
                    raise ConfigurationError(name + ': требуется список без повторов: ' + ', '.join(sorted(CLAUSES)))
                value = tuple(sorted(value))
            elif section == 'where':
                if type(value) is not bool:
                    raise ConfigurationError(name + ': требуется true или false')
            else:
                choices = {'case': ('upper', 'lower', 'preserve'),
                           'commas': ('leading', 'trailing'),
                           'group_by': ('multiline', 'inline', 'preserve')}[section]
                if type(value) is not str or value not in choices:
                    raise ConfigurationError(name + ': допустимы ' + ', '.join(choices))
            values.append((key, value))
        result.append((section, tuple(sorted(values))))
    return Settings(tuple(sorted(result)))


def parse_personal(raw):
    try:
        data = tomllib.loads(raw.decode('utf-8-sig'))
    except (UnicodeError, tomllib.TOMLDecodeError) as exc:
        # TOML parser messages can quote arbitrary user content: do not forward.
        raise ConfigurationError('personal.toml: неверная кодировка UTF-8 или синтаксис TOML (включая дубли ключей)') from exc
    return validate(data)


def load_personal():
    try:
        path = personal_path()
        if path is None:
            return None
        return parse_personal(path.read_bytes())
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ConfigurationError('personal.toml: файл отсутствует или недоступен для чтения') from exc


def differences(personal, corporate):
    return tuple(f'{section}.{key}' for section, values in personal.values for key, value in values
                 if value != corporate.get(section, key))


_CURRENT = ContextVar('sql_formatter_settings', default=None)


def current_settings():
    settings = _CURRENT.get()
    if settings is None:
        from formatter_modules.corporate_profile import CORPORATE
        return CORPORATE
    return settings


@contextmanager
def use_settings(settings):
    if not isinstance(settings, Settings):
        raise TypeError('Resolved Settings required')
    token = _CURRENT.set(settings)
    try:
        yield settings
    finally:
        _CURRENT.reset(token)
