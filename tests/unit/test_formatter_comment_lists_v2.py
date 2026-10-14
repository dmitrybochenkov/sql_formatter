import unittest
from test_formatter_comment_lists import clause
from formatter_modules.formatter_comment_lists_v2 import commented_select_edits
from formatter_modules.formatter_edits import apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans

class InlineCommentTests(unittest.TestCase):
    def run_case(self, sql, expected):
        a = sql.index('a', sql.index('SELECT') + 6)
        b = sql.rfind('b')
        c = sql.index(',')
        tree = clause(sql, [(a, a + 1), (b, b + 1)], [(c, c + 1)])
        edits = commented_select_edits(sql, tree)
        self.assertIsNotNone(edits)
        protected = [(p.start, p.end) for p in protected_spans(sql)]
        accepted, warnings = plan_edits(sql, edits, protected)
        self.assertEqual(warnings, [])
        self.assertEqual(apply_edits(sql, accepted), expected)

    def test_inline_comment(self):
        self.run_case('SELECT a, -- note\nb', 'SELECT\n    a -- note\n    , b')

    def test_inline_comment_indented(self):
        self.run_case('SELECT a,  -- note\n   b', 'SELECT\n    a  -- note\n    , b')

    def test_inline_comment_preserves_literal(self):
        sql = "SELECT 'a,b', -- note\n b"
        a = sql.index("'a,b'")
        b = sql.rfind('b')
        c = sql.index(',', a+5)
        tree = clause(sql, [(a, a+5), (b, b+1)], [(c, c+1)])
        edits = commented_select_edits(sql, tree)
        self.assertIsNotNone(edits)
        self.assertEqual(apply_edits(sql, edits), "SELECT\n    'a,b' -- note\n    , b")

    def test_ambiguous_comment_skipped(self):
        sql = 'SELECT a, -- note\n\nb'
        tree = clause(sql, [(7, 8), (len(sql)-1, len(sql))], [(8, 9)])
        self.assertIsNone(commented_select_edits(sql, tree))

if __name__ == '__main__':
    unittest.main()
