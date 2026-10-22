"""Small assertions for public byte-preservation guarantees."""
from formatter_modules.formatter_protection import protected_spans


def assert_protected_spans_preserved(test, source, result):
    """Compare kind, order, count and exact text, including CR/LF and quotes."""
    test.assertEqual(
        [(span.kind, source[span.start:span.end]) for span in protected_spans(source)],
        [(span.kind, result[span.start:span.end]) for span in protected_spans(result)],
    )
