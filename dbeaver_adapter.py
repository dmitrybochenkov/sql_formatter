"""Quiet file-to-UTF-8 transport for DBeaver's merged output stream."""
import contextlib
from datetime import datetime, timezone
import io
import json
import os
from pathlib import Path
import sys
import tempfile


def log_event(code, category):
    """Best effort, bounded, SQL-free diagnostics; never log exception messages."""
    try:
        directory = Path(os.environ.get('SQL_FORMATTER_LOG_DIR') or
                         str(Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir()) /
                             'SQLFormatter' / 'logs'))
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'adapter.jsonl'
        if path.exists() and path.stat().st_size > 262144:
            path.replace(directory / 'adapter.previous.jsonl')
        with path.open('a', encoding='utf-8', newline='\n') as stream:
            stream.write(json.dumps({'time': datetime.now(timezone.utc).isoformat(),
                                     'code': code, 'type': category,
                                     'description': 'See adapter documentation for this code.'}) + '\n')
    except Exception:
        pass


def format_bytes(original):
    """Retain original bytes until formatting AND strict validation succeed."""
    output = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
    errors = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
    try:
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            from formatter import format_sql, validate_sql_unchanged
            source = original.decode('utf-8-sig')
            diagnostics = []
            result = format_sql(source, diagnostics=diagnostics)
            codes = {d.code for d in diagnostics}
            known = {'SQLFMT-C001', 'SQLFMT-E001', 'SQLFMT-E002', 'SQLFMT-E003', 'SQLFMT-E004'}
            for code in sorted(codes & known):
                log_event(code, 'Diagnostic')
            if codes - known or codes & {'SQLFMT-E003', 'SQLFMT-E004'}:
                log_event('ADAPTER-REFUSAL', 'ConservativeRefusal')
                return original
            validate_sql_unchanged(source, result)
            encoded = result.encode('utf-8')
            output.flush()
            errors.flush()
            if output.buffer.getvalue() or errors.buffer.getvalue():
                log_event('ADAPTER-OUTPUT', 'UnexpectedOutput')
                return original
            return encoded
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        category = type(exc).__name__ if type(exc).__module__ == 'builtins' else 'Exception'
        log_event('ADAPTER-FORMAT', category)
        return original
    finally:
        output.close()
        errors.close()


def main():
    # Silence even native writes/import failures. Only the saved descriptor may
    # carry the completed result. Do not reconfigure streams during import.
    destination = None
    try:
        destination = os.dup(1)
        if os.name == 'nt':
            import msvcrt
            msvcrt.setmode(destination, os.O_BINARY)
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), 1)
            os.dup2(sink.fileno(), 2)
        if len(sys.argv) != 2:
            log_event('ADAPTER-ARGS', 'ArgumentError')
            return 2
        try:
            original = Path(sys.argv[1]).read_bytes()
        except Exception:
            log_event('ADAPTER-READ', 'ReadError')
            return 1
        result = format_bytes(original)
        try:
            remaining = memoryview(result)
            while remaining:
                written = os.write(destination, remaining)
                if written <= 0:
                    raise OSError('Output unavailable')
                remaining = remaining[written:]
        except Exception:
            # Never append fallback after a partial pipe write.
            log_event('ADAPTER-WRITE', 'WriteError')
            return 1
        return 0
    except BaseException:
        log_event('ADAPTER-START', 'StartupError')
        return 1
    finally:
        if destination is not None:
            try:
                os.close(destination)
            except OSError:
                pass


if __name__ == '__main__':
    sys.exit(main())
