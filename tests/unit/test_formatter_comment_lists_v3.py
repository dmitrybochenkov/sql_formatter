import unittest
from .test_formatter_comment_lists import clause
from formatter_modules.formatter_comment_lists_v3 import commented_select_edits
from formatter_modules.formatter_edits import apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans


class CommentListStage9Tests(unittest.TestCase):
    def check(self, source, expected, items, commas):
        tree = clause(source, [(source.index(x), source.index(x) + len(x)) for x in items],
                      [(source.index(','), source.index(',') + 1)] if commas else [])
        edits = commented_select_edits(source, tree)
        self.assertIsNotNone(edits)
        accepted, warnings = plan_edits(source, edits, [(p.start, p.end) for p in protected_spans(source)])
        self.assertEqual(warnings, [])
        self.assertEqual(apply_edits(source, accepted), expected)

    def test_comment_before_second_item(self):
        self.check('SELECT a\n-- note\n, b', 'SELECT\n    a\n    -- note\n    , b', ['a', 'b'], True)

    def test_two_comments_before_item(self):
        self.check('SELECT a\n-- first\n-- second\n, b',
                   'SELECT\n    a\n    -- first\n    -- second\n    , b', ['a', 'b'], True)

    def test_comment_before_first_item(self):
        self.check('SELECT\n-- note\na', 'SELECT\n    -- note\n    a', ['a'], False)

    def test_ambiguous_blank_line(self):
        source = 'SELECT a\n-- note\n\n, b'
        tree = clause(source, [(7, 8), (len(source)-1, len(source))],
                      [(source.index(','), source.index(',')+1)])
        self.assertIsNone(commented_select_edits(source, tree))


if __name__ == '__main__':
    unittest.main()
