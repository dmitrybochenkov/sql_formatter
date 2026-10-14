import unittest
from formatter_modules.formatter_protection import protected_spans, ambiguous_comment_spans
from formatter_modules.formatter_edits import Edit, plan_edits

class ProtectionTests(unittest.TestCase):
    def test_comments_inside_literals_are_not_comments(self):
        sql = "SELECT '-- hi', '/* no */', x -- real\nFROM t"
        self.assertEqual([s.kind for s in protected_spans(sql)], ['literal', 'literal', 'line_comment'])

    def test_escaped_quotes(self):
        sql = "SELECT 'it''s -- text', \"col\"\"name\" FROM t"
        self.assertEqual([s.kind for s in protected_spans(sql)], ['literal', 'quoted_identifier'])

    def test_block_comment(self):
        self.assertEqual([s.kind for s in protected_spans('a /* b\nc */ d')], ['block_comment'])

    def test_unterminated_comment_protected(self):
        sql = 'SELECT a /* open'
        self.assertEqual(protected_spans(sql)[0].end, len(sql))

    def test_edit_over_literal_is_rejected(self):
        sql = "SELECT 'x' FROM t"
        spans = protected_spans(sql)
        edits, warnings = plan_edits(sql, [Edit(0, len(sql), 'X', 'AST')], protected=[(s.start,s.end) for s in spans])
        self.assertFalse(edits)
        self.assertEqual(warnings[0].code, 'SQLFMT-E002')

    def test_ambiguous_detached_comment(self):
        sql = 'SELECT a\n\n-- note\n\nFROM t'
        self.assertEqual(len(ambiguous_comment_spans(sql)), 1)

    def test_adjacent_comment_is_not_ambiguous(self):
        sql = 'SELECT\n    -- note\n    a\nFROM t'
        self.assertFalse(ambiguous_comment_spans(sql))

if __name__ == '__main__':
    unittest.main()
