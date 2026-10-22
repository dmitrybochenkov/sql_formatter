"""Regression coverage: qualify. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B54QualifyTests(unittest.TestCase):
    def check_qualify(self, source, expected, codes=()):
        from sqlfluff.core import Linter
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        d1,d2=[],[]
        first = format_sql(source, diagnostics=d1)
        self.assertEqual(first, expected)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        self.assertEqual([(p.kind, source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind, first[p.start:p.end]) for p in protected_spans(first)])
        for diagnostics in (d1,d2):
            self.assertEqual([d.code for d in diagnostics], list(codes))
        def qualify_tokens(sql):
            tree = Linter(dialect='teradata').parse_string(sql).tree
            return [[(s.get_type(),s.raw) for s in q.raw_segments if s.is_code and not s.is_meta]
                    for q in tree.recursive_crawl('qualify_clause')]
        # Stronger than searching for the text '1=1': literals may contain it,
        # and existing tautologies must remain while no synthetic token is added.
        from formatter_modules.formatter_case import normalize_case
        self.assertEqual(qualify_tokens(normalize_case(source)), qualify_tokens(first))

    def test_three_old_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        from tests.fixtures.edge_cases import GOLDEN as EDGE
        for cases,key in ((GOLDEN,'qualify'),(V12,'qualify'),(EDGE,'qualify_two_conditions_no_synthetic_true')):
            self.check_qualify(*cases[key])

    def test_single_predicate_and_multiple_ands(self):
        self.check_qualify('SELECT a FROM t QUALIFY a=1;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1\n;\n')
        self.check_qualify('SELECT a FROM t qualify a=1 and b>2 and c<3;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1\n    AND b > 2\n    AND c < 3\n;\n')

    def test_or_and_mixed_boolean_expressions(self):
        self.check_qualify('SELECT a FROM t QUALIFY a=1 OR b=2;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1 OR b = 2\n;\n')
        self.check_qualify('SELECT a FROM t QUALIFY a=1 OR b=2 AND c=3;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1 OR b = 2 AND c = 3\n;\n', ('SQLFMT-W001',))

    def test_mixed_boolean_with_window_and_invalid_ast(self):
        self.check_qualify('SELECT a FROM t QUALIFY RANK() OVER (ORDER BY a)=1 OR a>0 AND b<2;',
            'SELECT\n    a\nFROM t\n\nQUALIFY RANK() OVER (\n    ORDER BY a\n) = 1 OR a > 0 AND b < 2\n;\n', ('SQLFMT-W001',))
        with self.assertRaises(ValueError):
            format_sql('SELECT a FROM t QUALIFY ;')

    def test_brackets_between_and_frame_ands(self):
        self.check_qualify('SELECT a FROM t QUALIFY (a=1 OR b=2) AND c BETWEEN 1 AND 3;',
            'SELECT\n    a\nFROM t\n\nQUALIFY (a = 1 OR b = 2)\n    AND c BETWEEN 1 AND 3\n;\n')
        self.check_qualify('SELECT a FROM t QUALIFY (a=1 AND b=2);',
            'SELECT\n    a\nFROM t\n\nQUALIFY (a = 1 AND b = 2)\n;\n')
        self.check_qualify('SELECT a FROM t QUALIFY SUM(a) OVER (ORDER BY b ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)>2;',
            'SELECT\n    a\nFROM t\n\nQUALIFY SUM(a) OVER (\n    ORDER BY b\n    ROWS BETWEEN 1 PRECEDING AND CURRENT ROW\n) > 2\n;\n')

    def test_multiple_windows_and_outer_order(self):
        self.check_qualify('SELECT a FROM t QUALIFY ROW_NUMBER() OVER (PARTITION BY a ORDER BY b)=1 AND SUM(c) OVER (ORDER BY b ROWS BETWEEN 1 PRECEDING AND CURRENT ROW)>2 ORDER BY a;',
            'SELECT\n    a\nFROM t\n\nQUALIFY ROW_NUMBER() OVER (\n    PARTITION BY a\n    ORDER BY b\n) = 1\n    AND SUM(c) OVER (\n        ORDER BY b\n        ROWS BETWEEN 1 PRECEDING AND CURRENT ROW\n    ) > 2\n\nORDER BY a\n;\n')

    def test_window_lists_and_rank(self):
        self.check_qualify('SELECT a FROM t QUALIFY RANK() OVER (PARTITION BY a,b ORDER BY c DESC NULLS LAST,d ASC)=1;',
            'SELECT\n    a\nFROM t\n\nQUALIFY RANK() OVER (\n    PARTITION BY\n        a\n        , b\n    ORDER BY\n        c DESC NULLS LAST\n        , d ASC\n) = 1\n;\n')

    def test_select_and_qualify_windows_have_separate_indentation(self):
        self.check_qualify('SELECT ROW_NUMBER() OVER (ORDER BY a) AS n FROM t QUALIFY RANK() OVER (ORDER BY b)=1;',
            'SELECT\n    ROW_NUMBER() OVER (\n        ORDER BY a\n    ) AS n\nFROM t\n\nQUALIFY RANK() OVER (\n    ORDER BY b\n) = 1\n;\n')

    def test_where_having_and_qualify_ownership(self):
        self.check_qualify('SELECT a FROM t WHERE p=1 AND q=2 GROUP BY a HAVING SUM(b)>1 AND COUNT(*)>2 QUALIFY a>3 AND a<9 ORDER BY a;',
            'SELECT\n    a\nFROM t\n\nWHERE 1=1\n    AND p = 1\n    AND q = 2\n\nGROUP BY a\n\nHAVING 1=1\n    AND SUM(b) > 1\n    AND COUNT(*) > 2\n\nQUALIFY a > 3\n    AND a < 9\n\nORDER BY a\n;\n')

    def test_cte_qualify(self):
        self.check_qualify('WITH c AS (SELECT a FROM t QUALIFY RANK() OVER (ORDER BY a)=1) SELECT a FROM c QUALIFY a>0;',
            'WITH c AS (\n    SELECT\n        a\n    FROM t\n\n    QUALIFY RANK() OVER (\n        ORDER BY a\n    ) = 1\n)\n\nSELECT\n    a\nFROM c\n\nQUALIFY a > 0\n;\n')

    def test_set_branches_qualify(self):
        self.check_qualify('SELECT a FROM t QUALIFY RANK() OVER (ORDER BY a)=1 UNION ALL SELECT b FROM u QUALIFY b>2 AND b<9 ORDER BY a;',
            'SELECT\n    a\nFROM t\n\nQUALIFY RANK() OVER (\n    ORDER BY a\n) = 1\n\nUNION ALL\n\nSELECT\n    b\nFROM u\n\nQUALIFY b > 2\n    AND b < 9\n\nORDER BY a\n;\n')

    def test_comments_before_between_and_after_conditions(self):
        self.check_qualify('SELECT a FROM t\n-- qualify\nQUALIFY a=1 -- first\nAND b=2 -- last\nORDER BY a;',
            'SELECT\n    a\nFROM t\n\n-- qualify\nQUALIFY a = 1 -- first\n    AND b = 2 -- last\n\nORDER BY a\n;\n')
        self.check_qualify('SELECT a FROM t QUALIFY /* header */ a=1 AND /* second */ b=2;',
            'SELECT\n    a\nFROM t\n\nQUALIFY /* header */ a = 1\n    AND /* second */ b = 2\n;\n')

        self.check_qualify('SELECT a FROM t QUALIFY a=1 -- last\n;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1 -- last\n;\n')

    def test_literals_function_arguments_and_keyword_case(self):
        self.check_qualify("SELECT a FROM t qualify SUM(CASE WHEN s='QUALIFY AND 1=1' THEN 1 ELSE 0 END) over (partition by a order by b)>0;",
            "SELECT\n    a\nFROM t\n\nQUALIFY SUM(CASE WHEN s='QUALIFY AND 1=1' THEN 1 ELSE 0 END) OVER (\n    PARTITION BY a\n    ORDER BY b\n) > 0\n;\n")

    def test_multiline_inputs(self):
        expected = 'SELECT\n    a\nFROM t\n\nQUALIFY RANK() OVER (\n    ORDER BY a\n) = 1\n    AND b > 0\n;\n'
        for source in ('SELECT a FROM t QUALIFY RANK() OVER(ORDER BY a)=1 AND b>0;',
                       '  SELECT a\n FROM t\n     QUALIFY RANK() OVER (\n ORDER BY a\n      )=1\n  AND b>0;'):
            self.check_qualify(source, expected)

    def test_existing_tautology_is_not_removed_or_duplicated(self):
        self.check_qualify('SELECT a FROM t QUALIFY 1=1 AND a>0;',
            'SELECT\n    a\nFROM t\n\nQUALIFY 1 = 1\n    AND a > 0\n;\n')

    def test_ambiguous_comments(self):
        self.check_qualify('SELECT a FROM t QUALIFY a=1\n-- detached\n\nAND b=2;',
            'SELECT\n    a\nFROM t\n\nQUALIFY a = 1\n-- detached\n\nAND b = 2\n;\n', ('SQLFMT-C001',))

    def test_named_windows_keep_e004_refusal(self):
        for source in ('SELECT a FROM t QUALIFY SUM(a) OVER w>1;',
                       'SELECT a FROM t QUALIFY SUM(a) OVER (w ORDER BY b,c)>1;'):
            self.check_qualify(source, source, ('SQLFMT-E004',))

    def test_atomic_edits_and_protected_spans(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import Edit,plan_edits,apply_edits
        from formatter_modules.formatter_protection import protected_spans
        source = "SELECT a FROM t QUALIFY RANK() OVER (PARTITION BY 'x,y',b ORDER BY c)=1 AND a>0;"
        tree=Linter(dialect='teradata').parse_string(source).tree
        edits,handled=nested_query_gap_edits(source,tree,include_simple=True,include_windows=True,include_qualify=True)
        self.assertEqual(handled,{0})
        self.assertTrue(edits)
        self.assertEqual(len({e.group_id for e in edits}),1)
        spans=[(p.start,p.end) for p in protected_spans(source)]
        accepted,warnings=plan_edits(source,edits,protected=spans)
        self.assertEqual(warnings,[])
        self.assertEqual(len(accepted),len(edits))
        reverse,warnings=plan_edits(source,list(reversed(edits)),protected=spans)
        self.assertEqual(warnings,[])
        self.assertEqual(apply_edits(source,accepted),apply_edits(source,reverse))
        e=next(e for e in edits if ',' in source[e.start:e.end])
        accepted,warnings=plan_edits(source,edits,protected=spans+[(e.start,e.end)])
        self.assertEqual(accepted,[])
        self.assertTrue(any(d.code=='SQLFMT-E002' for d in warnings))
        accepted,warnings=plan_edits(source,[Edit(e.start,e.start,' ','conflict')]+edits)
        self.assertIn(len([x for x in accepted if x.group_id==e.group_id]),(0,len(edits)))
        self.assertTrue(any(d.code=='SQLFMT-E001' for d in warnings))

    def test_strict_validator_rejects_qualify_changes(self):
        from formatter import validate_sql_unchanged
        source='SELECT a FROM t qualify a>1 AND b<2;'
        valid=format_sql(source)
        validate_sql_unchanged(source,valid)
        for invalid in (valid.replace('QUALIFY','Qualify'),valid.replace('QUALIFY','QUALIFY 1=1 AND'),
                        valid.replace('AND','OR'),valid.replace('a > 1','a > 2'),valid.replace('b < 2','b < 3')):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                validate_sql_unchanged(source,invalid)

if __name__ == "__main__":
    unittest.main()
