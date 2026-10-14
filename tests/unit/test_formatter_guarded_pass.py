import unittest
from formatter_modules.formatter_guarded_pass import guarded_pass


class GuardedPassTests(unittest.TestCase):
    def test_safe_whitespace_change(self):
        actual, warnings = guarded_pass('SELECT  a', lambda x: x.replace('  ', ' '), 'SPACE')
        self.assertEqual(actual, 'SELECT a')
        self.assertFalse(warnings)

    def test_preserves_line_comment(self):
        source = 'SELECT a -- keep  spaces\nFROM t'
        actual, warnings = guarded_pass(source, lambda x: x.replace('keep  spaces', 'keep spaces'), 'SPACE')
        self.assertEqual(actual, source)
        self.assertTrue(warnings)

    def test_preserves_literal(self):
        source = "SELECT 'a  b' FROM t"
        actual, warnings = guarded_pass(source, lambda x: x.replace('a  b', 'a b'), 'SPACE')
        self.assertEqual(actual, source)
        self.assertTrue(warnings)

    def test_formats_outside_literal(self):
        source = "SELECT  'a  b'"
        actual, warnings = guarded_pass(source, lambda x: x.replace('  ', ' '), 'SPACE')
        self.assertEqual(actual, "SELECT 'a  b'")
        self.assertTrue(warnings)

    def test_preserves_ambiguous_comment_gap(self):
        source = 'SELECT a\n-- detached\n\nFROM t'
        actual, warnings = guarded_pass(source, lambda x: x.replace('-- detached\n\nFROM', '-- detached\nFROM'), 'SPACE')
        self.assertEqual(actual, source)
        self.assertTrue(warnings)

    def test_idempotent_pass(self):
        f = lambda x: x.replace('  ', ' ')
        first, _ = guarded_pass('SELECT  a', f, 'SPACE')
        second, _ = guarded_pass(first, f, 'SPACE')
        self.assertEqual(first, second)


if __name__ == '__main__':
    unittest.main()
