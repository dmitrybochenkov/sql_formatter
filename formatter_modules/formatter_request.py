"""Bounded, synchronous-request memoization of value-only proof results.

Never stores SQLFluff ASTs, configs, linters, edits or complete format results.
The public operation still runs comparisons/layout/rollback on every call.
"""
from contextvars import ContextVar
from copy import deepcopy
from functools import wraps
from threading import get_ident

_CURRENT = ContextVar('formatter_proof_request', default=None)
_MAX_ENTRIES = 32
_MAX_SOURCE_CHARS = 200_000
_MAX_ENTRY_CHARS = 64_000


class _Request:
    def __init__(self):
        self.owner = get_ident()
        self.active = True
        self.values = {}
        self.source_chars = 0


def request_scope(function):
    """Nested synchronous calls share proofs; each top-level call starts fresh."""
    @wraps(function)
    def call(*args, **kwargs):
        current = _CURRENT.get()
        if current is not None and current.active and current.owner == get_ident():
            return function(*args, **kwargs)
        current = _Request()
        token = _CURRENT.set(current)
        try:
            return function(*args, **kwargs)
        finally:
            current.values.clear()
            current.active = False
            _CURRENT.reset(token)
    return call


def proof_memo(config_path=None):
    """Cache successful values for exact SQL + immutable effective settings.

    Caller results are defensive copies, including the first return. Source
    text and CR/LF are never canonicalized in a key. No cross-request retention.
    Optional config_path adds a lazy file namespace for standalone consumers;
    production uses only the resolved policy fingerprint, without file reads.
    """
    def decorate(function):
        @wraps(function)
        def call(source):
            current = _CURRENT.get()
            if (current is None or not current.active or current.owner != get_ident()
                    or len(source) > _MAX_ENTRY_CHARS):
                return function(source)
            try:
                from formatter_modules.formatter_config import current_settings
                path = config_path() if config_path is not None else None
                namespace = (str(path.resolve()), path.read_bytes()) if path is not None else ()
                key = (function, namespace, current_settings().fingerprint, source)
            except OSError:
                # Fingerprinting is optional work: preserve the original
                # loader's success/failure semantics (including its cache).
                return function(source)
            if key in current.values:
                return deepcopy(current.values[key])
            value = function(source)  # Exceptions are never memoized.
            if (len(current.values) < _MAX_ENTRIES
                    and current.source_chars + len(source) <= _MAX_SOURCE_CHARS):
                current.values[key] = deepcopy(value)
                current.source_chars += len(source)
            return value
        return call
    return decorate
