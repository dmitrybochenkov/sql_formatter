import unittest
from dataclasses import dataclass
from formatter_modules.formatter_comment_lists import commented_select_edits
from formatter_modules.formatter_edits import apply_edits

@dataclass
class Marker:
    source_slice: slice

class Seg:
    def __init__(self, kind, a, b, segments=()):
        self.kind, self.pos_marker, self.segments = kind, Marker(slice(a,b)), segments
    def is_type(self, *types):
        return self.kind in types

def clause(sql, fields, commas):
    return Seg('select_clause', 0, len(sql), [Seg('select_clause_element', *p) for p in fields] + [Seg('comma', *p) for p in commas])

class Tests(unittest.TestCase):
    def test_standalone_comment_before_leading_comma(self):
        sql = 'SELECT a\n-- explanation\n, b'
        tree = clause(sql, [(7,8), (len(sql)-1,len(sql))], [(sql.index(','), sql.index(',')+1)])
        edits = commented_select_edits(sql, tree)
        self.assertIsNotNone(edits)
        out = apply_edits(sql, edits)
        self.assertEqual(out, 'SELECT\n    a\n-- explanation\n, b')

    def test_trailing_comment_is_not_moved(self):
        sql = 'SELECT a -- explanation\n, b'
        tree = clause(sql, [(7,8), (len(sql)-1,len(sql))], [(sql.index(','), sql.index(',')+1)])
        self.assertIsNone(commented_select_edits(sql, tree))

    def test_comma_before_comment_not_reordered(self):
        sql = 'SELECT a, -- explanation\nb'
        tree = clause(sql, [(7,8), (len(sql)-1,len(sql))], [(sql.index(','), sql.index(',')+1)])
        self.assertIsNone(commented_select_edits(sql, tree))

if __name__ == '__main__':
    unittest.main()
