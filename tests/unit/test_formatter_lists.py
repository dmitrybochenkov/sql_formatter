import unittest
from types import SimpleNamespace
from formatter_modules.formatter_lists import normalize_simple_list


class Segment:
    def __init__(self, typ, start, end, children=()):
        self.typ = typ
        self.pos_marker = SimpleNamespace(source_slice=slice(start, end))
        self.segments = children

    def is_type(self, *types):
        return self.typ in types


def clause(sql, kind, expressions, comma_positions=(), children=()):
    parts = [Segment('select_clause_element' if kind == 'select_clause' else 'orderby_clause_element', a, b)
             for a, b in expressions]
    parts += [Segment('comma', p, p + 1) for p in comma_positions]
    return Segment(kind, 0, len(sql), parts + list(children))


class ListTests(unittest.TestCase):
    def test_select_random_whitespace(self):
        sql = 'SELECT   a,   b, c'
        c = clause(sql, 'select_clause', [(9,10),(14,15),(17,18)], [10,15])
        edit = normalize_simple_list(sql, c)
        self.assertEqual(edit.replacement, 'SELECT\n    a\n    , b\n    , c')

    def test_distinct_spelling(self):
        sql = 'select distinct   t.id, t.name'
        c = clause(sql, 'select_clause', [(18,22),(24,30)], [22])
        self.assertEqual(normalize_simple_list(sql,c).replacement,
                         'select distinct\n    t.id\n    , t.name')

    def test_nested_expression_preserved(self):
        sql = 'SELECT SUM(a,b), id'
        c = clause(sql,'select_clause',[(7,15),(17,19)],[15])
        self.assertEqual(normalize_simple_list(sql,c).replacement,
                         'SELECT\n    SUM(a,b)\n    , id')

    def test_comment_skips(self):
        sql = 'SELECT a -- comment\n, b'
        c = clause(sql,'select_clause',[(7,8),(22,23)],[20],
                   [Segment('inline_comment',9,19)])
        self.assertIsNone(normalize_simple_list(sql,c))

    def test_multiline_expression_skips(self):
        sql = 'SELECT CASE\n WHEN x THEN y END, b'
        c = clause(sql,'select_clause',[(7,29),(31,32)],[29])
        self.assertIsNone(normalize_simple_list(sql,c))

    def test_idempotent_simple(self):
        sql = 'SELECT\n    a\n    , b'
        c = clause(sql,'select_clause',[(11,12),(19,20)],[17])
        self.assertIsNone(normalize_simple_list(sql,c))


if __name__ == '__main__':
    unittest.main()
