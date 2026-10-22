"""Three unique inputs retained from the retired preserve-layout helper.

Public contract: preserve comment text/attachment; normalize only proven whitespace.
Historical helper refusal is not a public formatter refusal (B10.3d audit).
"""
import unittest
from formatter import format_sql, validate_sql_unchanged
from tests.helpers.assertions import assert_protected_spans_preserved


class CommentAttachmentTests(unittest.TestCase):
    def check_attachment(self, source, anchor):
        diagnostics = []
        result = format_sql(source, diagnostics=diagnostics)
        self.assertEqual(diagnostics, [])
        self.assertIn(anchor, result)
        self.assertEqual(result.count('-- explanation'), 1)
        validate_sql_unchanged(source, result)
        assert_protected_spans_preserved(self, source, result)
        repeated_diagnostics = []
        self.assertEqual(format_sql(result, diagnostics=repeated_diagnostics), result)
        self.assertEqual(repeated_diagnostics, [])

    def test_standalone_comment_before_leading_comma(self):
        self.check_attachment('SELECT a\n-- explanation\n, b',
                              '    a\n    -- explanation\n    , b')

    def test_trailing_comment_is_not_moved(self):
        self.check_attachment('SELECT a -- explanation\n, b',
                              'a -- explanation\n    , b')

    def test_trailing_comma_moves_without_detaching_comment(self):
        # Move the comma, never the comment: it still belongs to a.
        self.check_attachment('SELECT a, -- explanation\nb',
                              '    a -- explanation\n    , b')
