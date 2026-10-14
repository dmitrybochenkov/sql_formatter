import unittest
from types import SimpleNamespace
from formatter_modules.formatter_clause_gaps import clause_gap_edits
from formatter_modules.formatter_edits import apply_edits

class Segment:
    def __init__(self, kind, start, stop, children=()):
        self.kind = kind
        self.pos_marker = SimpleNamespace(source_slice=slice(start, stop))
        self.segments = list(children)
    def is_type(self, *kinds):
        return self.kind in kinds

def clause(sql, kind, comma_positions=(), children=()):
    return Segment(kind, 0, len(sql), list(children) + [Segment('comma', x, x+1) for x in comma_positions])

class ClauseGapTests(unittest.TestCase):
    def check(self, sql, kind, expected, commas=()):
        edits = clause_gap_edits(sql, clause(sql, kind, commas))
        self.assertIsNotNone(edits)
        self.assertEqual(apply_edits(sql, edits), expected)
        self.assertEqual(clause_gap_edits(expected, clause(expected, kind, [i for i,c in enumerate(expected) if c==',' and expected[:i].count('(')==expected[:i].count(')')])), [])
    def test_group_multiple(self):
        self.check('GROUP BY a, b', 'groupby_clause', 'GROUP BY\n    a\n    , b', (10,))
    def test_order_multiple(self):
        self.check('ORDER BY a DESC, b ASC', 'orderby_clause', 'ORDER BY\n    a DESC\n    , b ASC', (15,))
    def test_group_single(self):
        self.check('GROUP   BY  a', 'groupby_clause', 'GROUP BY a')
    def test_from_single(self):
        self.check('FROM    users t', 'from_clause', 'FROM users t')
    def test_from_multiple(self):
        self.check('FROM users a, payments b', 'from_clause', 'FROM users a\n    , payments b', (12,))
    def test_comment_skipped(self):
        sql = 'GROUP BY a -- note\n, b'
        self.assertIsNone(clause_gap_edits(sql, clause(sql,'groupby_clause',(19,))))
    def test_join_skipped(self):
        sql = 'FROM users a JOIN payments b ON a.id = b.id'
        nested = Segment('join_clause',13,len(sql))
        self.assertIsNone(clause_gap_edits(sql, clause(sql,'from_clause',children=(nested,))))
    def test_function_comma_not_split(self):
        sql = 'GROUP BY COALESCE(a, b), c'
        self.check(sql,'groupby_clause','GROUP BY\n    COALESCE(a, b)\n    , c',(23,))

if __name__ == '__main__': unittest.main()
