"""SQL-free change notices, user-local state and OS advisory locking."""
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile

from formatter_modules import formatter_config as config
from formatter_modules.corporate_profile import CORPORATE

@dataclass(frozen=True)
class PersonalState:
    settings: object
    digest: str
    differences: tuple
    error: str | None
    present: bool = True

    @property
    def message(self):
        if self.error:
            return ('Ошибка в Personal: ' + self.error +
                    '. Используется Corporate. Выбор профиля отключён до исправления ошибки.')
        if not self.differences:
            return ('Настройки Personal корректны. Отличий от Corporate нет. '
                    'Форматирование выполняется без выбора профиля.')
        return ('Настройки Personal корректны. Найдено отличий от Corporate: '
                + str(len(self.differences)) + '. Будет предложен выбор профиля.\n\n'
                + '\n'.join(self.differences))


def read_state():
    try:
        path = config.personal_path()
        if path is None:
            return PersonalState(None, '', (), None, present=False)
        raw = path.read_bytes()
    except FileNotFoundError:
        return PersonalState(None, '', (), None, present=False)
    except OSError:
        return PersonalState(None, hashlib.sha256(b'unreadable').hexdigest(), (),
                             'personal.toml: файл отсутствует или недоступен для чтения')
    digest = hashlib.sha256(raw).hexdigest()
    try:
        settings = config.parse_personal(raw)
        return PersonalState(settings, digest, config.differences(settings, CORPORATE), None)
    except config.ConfigurationError as exc:
        return PersonalState(None, digest, (), 'personal.toml: недопустимая конфигурация')


def state_path():
    directory = config.user_config_directory()
    return directory / 'profile_state.json' if directory is not None else None


@contextmanager
def locked(path):
    """Crash-released kernel lock. Busy => defer notice, never race two windows."""
    stream = path.open('a+b')
    acquired = False
    try:
        if os.name == 'nt':
            import msvcrt
            stream.seek(0, 2)
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                acquired = True
            except OSError:
                pass
        else:
            import fcntl
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
            except BlockingIOError:
                pass
        yield acquired
    finally:
        if acquired:
            if os.name == 'nt':
                stream.seek(0); msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)
        stream.close()


def notify_changed(state, show):
    """Return whether a notice was needed/shown. GUI errors propagate fail-safe."""
    installation = hashlib.sha256(str(config.personal_path()).encode()).hexdigest()
    record = {'hash': state.digest, 'corporate': CORPORATE.fingerprint}

    def needs(previous):
        if previous == record:
            return False
        if not state.present or (previous is None and not state.error and not state.differences):
            return False
        return True

    path = state_path()
    if path is None:
        if needs(None):
            return bool(show(state.message))
        return False
    if not state.present and not path.exists():
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        lock = locked(path.with_suffix('.lock'))
        acquired = lock.__enter__()
    except OSError:
        if needs(None):
            return bool(show(state.message))
        return False
    try:
        if not acquired:
            return False
        try:
            saved = json.loads(path.read_text(encoding='utf-8'))
            if saved.get('version') != 1 or not isinstance(saved.get('installations'), dict):
                saved = {'version': 1, 'installations': {}}
        except (OSError, ValueError, AttributeError):
            saved = {'version': 1, 'installations': {}}
        previous = saved['installations'].get(installation)
        needed = needs(previous)
        if needed and not show(state.message):
            return False
        if state.present:
            if previous == record:
                return False
            saved['installations'][installation] = record
        else:
            if installation not in saved['installations']:
                return False
            del saved['installations'][installation]
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                             prefix='profile_state.', suffix='.tmp', delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(saved, stream, ensure_ascii=True)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError:
            pass  # Delivery succeeded; a future invocation may notify again.
        finally:
            if temporary is not None:
                try:
                    temporary.unlink(missing_ok=True)
                except OSError:
                    pass
        return needed
    finally:
        lock.__exit__(None, None, None)
