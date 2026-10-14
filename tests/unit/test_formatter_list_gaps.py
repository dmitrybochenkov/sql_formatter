import unittest
from types import SimpleNamespace
from formatter_modules.formatter_list_gaps import select_gap_edits
from formatter_modules.formatter_edits import apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans

class S:
    def __init__(self, typ, a, b, children=()):
        self.typ = typ
        self.pos_marker = SimpleNamespace(source_slice=slice(a,b))
        self.segments = children
    def is_type(self,*names): return self.typ in names

def make(sql, parts):
    els = [S('select_clause_element',a,b) for a,b in parts]
    commas = [S('comma',i,i+1) for i,c in enumerate(sql) if c==',' and not any(a<=i<b for a,b in parts)]
    return S('select_clause',0,len(sql),els+commas)

class GapTests(unittest.TestCase):
    def run_case(self, sql, expressions, expected):
        edits = select_gap_edits(sql, make(sql, expressions))
        self.assertIsNotNone(edits)
        accepted, warnings = plan_edits(sql, edits, [(p.start,p.end) for p in protected_spans(sql)])
        self.assertFalse(warnings)
        self.assertEqual(apply_edits(sql, accepted), expected)
    def test_literal(self):
        sql = "SELECT  'a,b' ,  id"
        self.run_case(sql, [(8,13),(17,19)], "SELECT\n    'a,b'\n    , id")
    def test_quoted_identifier(self):
        sql = 'SELECT  "some name", x'
        self.run_case(sql,[(8,19),(21,22)], 'SELECT\n    "some name"\n    , x')
    def test_comment_is_not_moved(self):
        sql = 'SELECT a -- note\n, b'
        self.assertIsNone(select_gap_edits(sql,make(sql,[(7,8),(20,21)])))
    def test_no_rewrite_inside_expression(self):
        sql = "SELECT 'x  y',  a+b"
        self.run_case(sql,[(7,13),(16,19)],"SELECT\n    'x  y'\n    , a+b")
    def test_idempotent(self):
        sql = "SELECT\n    'a'\n    , b"
        self.assertEqual(select_gap_edits(sql,make(sql,[(11,14),(21,22)])),[])

if __name__=='__main__': unittest.main()
