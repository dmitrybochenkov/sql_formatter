"""Private Unicode identifier extension; no normalization or SQL masking.

Character categories follow Teradata SQL Fundamentals / Object Names. Server
session character set, NameValidationRule and catalog limits are server checks.
"""
from sqlfluff.core.parser import (
    RegexLexer, RegexParser, WordSegment, IdentifierSegment, SegmentGenerator,
)

START = r'\p{L}\p{Nl}_#$\u00a1\u203e\u20ac\u309b\u309c\uff03\uff04\uff3f'
EXTEND = START + r'\p{Mn}\p{Mc}\p{Nd}\p{Pc}\p{Cf}\u00b7'
# Keep the existing ASCII grammar branch unchanged for compatibility.
# RegexParser uses IGNORECASE; the non-ASCII test must not fold U+0130 to I.
IDENTIFIER = (r'(?:(?=[' + EXTEND + r']*(?-i:[^\x00-\x7f]))[' + START + r'][' + EXTEND
              + r']*|[A-Z0-9_]*[A-Z][A-Z0-9_]*)')


def add_unicode_identifiers(dialect):
    dialect.patch_lexer_matchers([
        RegexLexer('word', '[' + EXTEND + ']+', WordSegment),
    ])
    dialect.replace(NakedIdentifierSegment=SegmentGenerator(
        lambda d: RegexParser(
            IDENTIFIER, IdentifierSegment, type='naked_identifier',
            anti_template=r'^(?:' + '|'.join(sorted(d.sets('reserved_keywords'))) + r')$',
            casefold=str.upper)))
    return dialect
