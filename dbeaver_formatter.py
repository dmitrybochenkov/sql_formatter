import sys
from pathlib import Path

from formatter import format_sql


def main():
    if len(sys.argv) != 2:
        print("Expected SQL file path", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])

    try:
        from formatter_modules.formatter_dialect import decode_sql_bytes
        source = decode_sql_bytes(path.read_bytes())

        # # Сохраняем входной SQL для диагностики.
        # debug_path = Path(__file__).resolve().parent / "dbeaver_debug.sql"
        # debug_path.write_text(source, encoding="utf-8")

        result = format_sql(source)

        # DBeaver получит только отформатированный SQL.
        sys.stdout.buffer.write(result.encode("utf-8"))
        return 0

    except (OSError, UnicodeError, ValueError) as exc:
        print(
            f"Formatting failed: {str(exc).encode('unicode_escape').decode('ascii')}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
