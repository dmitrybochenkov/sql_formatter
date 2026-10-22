"""Regression coverage: windows. Historical class IDs retain provenance."""
import unittest
from formatter import format_sql

class B53WindowTests(unittest.TestCase):
    def check_window(self, source, expected):
        from formatter import validate_sql_unchanged
        from formatter_modules.formatter_protection import protected_spans
        d1, d2 = [], []
        first = format_sql(source, diagnostics=d1)
        self.assertEqual(first, expected)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        self.assertEqual([(p.kind, source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind, first[p.start:p.end]) for p in protected_spans(first)])
        self.assertEqual(d1, [])
        self.assertEqual(d2, [])

    def test_two_old_goldens(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.golden import GOLDEN as V12
        for cases in (GOLDEN, V12):
            self.check_window(*cases['window_multiple_keys'])

    def test_simple_and_empty_window(self):
        self.check_window('SELECT ROW_NUMBER() OVER (ORDER BY a) AS n FROM t;',
            'SELECT\n    ROW_NUMBER() OVER (\n        ORDER BY a\n    ) AS n\nFROM t\n;\n')
        self.check_window('SELECT SUM(a) OVER () AS n FROM t;',
            'SELECT\n    SUM(a) OVER (\n    ) AS n\nFROM t\n;\n')

    def test_multiple_windows_and_outer_order(self):
        self.check_window('SELECT SUM(a+b) OVER (PARTITION BY a ORDER BY b ROWS BETWEEN 6 PRECEDING AND CURRENT ROW) AS n, ROW_NUMBER() OVER (ORDER BY a DESC NULLS LAST) AS rn FROM t ORDER BY a;',
            'SELECT\n    SUM(a+b) OVER (\n        PARTITION BY a\n        ORDER BY b\n        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW\n    ) AS n\n    , ROW_NUMBER() OVER (\n        ORDER BY a DESC NULLS LAST\n    ) AS rn\nFROM t\n\nORDER BY a\n;\n')

    def test_partition_and_order_expression_lists(self):
        self.check_window('SELECT SUM(a) OVER (PARTITION BY COALESCE(a,b),c ORDER BY d ASC NULLS FIRST,e DESC NULLS LAST) AS n FROM t;',
            'SELECT\n    SUM(a) OVER (\n        PARTITION BY\n            COALESCE(a,b)\n            , c\n        ORDER BY\n            d ASC NULLS FIRST\n            , e DESC NULLS LAST\n    ) AS n\nFROM t\n;\n')

    def test_rows_range_frames_are_opaque(self):
        for frame in ('ROWS BETWEEN 2 PRECEDING AND CURRENT ROW',
                      'ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING',
                      'RANGE BETWEEN 1 PRECEDING AND 2 FOLLOWING',
                      'rows  3 preceding', 'RANGE CURRENT ROW'):
            with self.subTest(frame=frame):
                self.check_window(f'SELECT SUM(a) OVER (ORDER BY b {frame}) AS n FROM t;',
                    f'SELECT\n    SUM(a) OVER (\n        ORDER BY b\n        {frame.upper()}\n    ) AS n\nFROM t\n;\n')

    def test_arguments_literals_and_case_are_opaque(self):
        self.check_window("SELECT SUM(CASE WHEN s='ORDER BY, OVER' THEN 1 ELSE 0 END) over (partition by COALESCE(a+b,'x,y'),s order by c range between unbounded preceding and current row) AS n FROM t;",
            "SELECT\n    SUM(CASE WHEN s='ORDER BY, OVER' THEN 1 ELSE 0 END) OVER (\n        PARTITION BY\n            COALESCE(a+b,'x,y')\n            , s\n        ORDER BY c\n        RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW\n    ) AS n\nFROM t\n;\n")
        self.check_window('SELECT SUM(a /* arg */ +  b) OVER (PARTITION BY a) AS n FROM t;',
            'SELECT\n    SUM(a /* arg */ +  b) OVER (\n        PARTITION BY a\n    ) AS n\nFROM t\n;\n')

    def test_multiline_function_arguments_and_nested_query(self):
        self.check_window('SELECT SUM(\n a+  b\n) OVER (ORDER BY c) AS n FROM t;',
            'SELECT\n    SUM(\n a+  b\n) OVER (\n        ORDER BY c\n    ) AS n\nFROM t\n;\n')
        self.check_window('SELECT a FROM (SELECT ROW_NUMBER() OVER (ORDER BY b) AS a FROM u) s;',
            'SELECT\n    a\nFROM (\n    SELECT\n        ROW_NUMBER() OVER (\n            ORDER BY b\n        ) AS a\n    FROM u\n) s\n;\n')

    def test_mixed_comment_chain_refuses_list_edits(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT SUM(a) OVER (PARTITION BY a, -- trailing\n-- standalone\nb ORDER BY c) AS n FROM t;'
        d1,d2=[],[]
        first = format_sql(source, diagnostics=d1)
        self.assertIn('PARTITION BY a, -- trailing\n-- standalone\nb', first)
        self.assertEqual(format_sql(first, diagnostics=d2), first)
        validate_sql_unchanged(source, first)
        for diagnostics in (d1,d2):
            self.assertTrue(any(d.code == 'SQLFMT-C001' for d in diagnostics))
            self.assertFalse(any(d.code in ('SQLFMT-E001','SQLFMT-E002') for d in diagnostics))

    def test_where_group_having_and_outer_order(self):
        self.check_window('SELECT a,SUM(a) OVER (ORDER BY a) AS n FROM t WHERE p=1 AND q=2 GROUP BY a HAVING SUM(a)>1 AND COUNT(*)>2 ORDER BY a;',
            'SELECT\n    a\n    , SUM(a) OVER (\n        ORDER BY a\n    ) AS n\nFROM t\n\nWHERE 1=1\n    AND p = 1\n    AND q = 2\n\nGROUP BY a\n\nHAVING 1=1\n    AND SUM(a) > 1\n    AND COUNT(*) > 2\n\nORDER BY a\n;\n')

    def test_cte_window(self):
        self.check_window('WITH c AS (SELECT ROW_NUMBER() OVER (ORDER BY a) AS n FROM t) SELECT n FROM c;',
            'WITH c AS (\n    SELECT\n        ROW_NUMBER() OVER (\n            ORDER BY a\n        ) AS n\n    FROM t\n)\n\nSELECT\n    n\nFROM c\n;\n')

    def test_set_operation_windows(self):
        self.check_window('SELECT SUM(a) OVER (ORDER BY a) AS n FROM t UNION ALL SELECT SUM(b) OVER (PARTITION BY c) AS n FROM u ORDER BY n;',
            'SELECT\n    SUM(a) OVER (\n        ORDER BY a\n    ) AS n\nFROM t\n\nUNION ALL\n\nSELECT\n    SUM(b) OVER (\n        PARTITION BY c\n    ) AS n\nFROM u\n\nORDER BY n\n;\n')

    def test_multiline_and_compact_inputs(self):
        expected = 'SELECT\n    ROW_NUMBER() OVER (\n        PARTITION BY a\n        ORDER BY b\n    ) AS n\nFROM t\n;\n'
        for source in ('select ROW_NUMBER() over(partition by a order by b) AS n from t;',
                       '   select\n  ROW_NUMBER() over (\n partition by a\n     order by b\n     ) AS n\n  from t;'):
            self.check_window(source, expected)

    def test_list_comments(self):
        self.check_window('SELECT SUM(a) OVER (PARTITION BY a,\n-- next\nb ORDER BY c, /* tail */\nd) AS n FROM t;',
            'SELECT\n    SUM(a) OVER (\n        PARTITION BY\n            a\n            -- next\n            , b\n        ORDER BY\n            c /* tail */\n            , d\n    ) AS n\nFROM t\n;\n')

    def test_boundary_and_frame_comments(self):
        self.check_window('SELECT SUM(a) OVER (\n-- head\nPARTITION BY a ORDER BY b ROWS BETWEEN 1 PRECEDING /* keep\n bytes */ AND CURRENT ROW\n-- close\n) AS n FROM t;',
            'SELECT\n    SUM(a) OVER (\n        -- head\n        PARTITION BY a\n        ORDER BY b\n        ROWS BETWEEN 1 PRECEDING /* keep\n bytes */ AND CURRENT ROW\n    -- close\n    ) AS n\nFROM t\n;\n')

    def test_comment_next_to_window_expression(self):
        self.check_window('SELECT a,\n-- window\nROW_NUMBER() OVER (ORDER BY b) AS n FROM t;',
            'SELECT\n    a\n    -- window\n    , ROW_NUMBER() OVER (\n        ORDER BY b\n    ) AS n\nFROM t\n;\n')

    def test_ambiguous_list_comment_is_not_moved(self):
        from formatter import validate_sql_unchanged
        for part in ('PARTITION BY', 'ORDER BY'):
            source = f'SELECT SUM(a) OVER ({part} a,\n-- detached\n\nb) AS n FROM t;'
            d1,d2=[],[]
            first = format_sql(source, diagnostics=d1)
            self.assertIn(f'{part} a,\n-- detached\n\nb', first)
            self.assertEqual(format_sql(first, diagnostics=d2), first)
            validate_sql_unchanged(source, first)
            for diagnostics in (d1,d2):
                self.assertTrue(any(d.code == 'SQLFMT-C001' for d in diagnostics))
                self.assertFalse(any(d.code == 'SQLFMT-E001' for d in diagnostics))
                # The unchanged guarded postpass refuses to remove the detached
                # blank line inside this SELECT. Its E002 is a safety refusal.
                self.assertTrue(all('SELECT-BLANKLINES' in d.message
                                    for d in diagnostics if d.code == 'SQLFMT-E002'))

    def test_atomic_window_edits(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import Edit, plan_edits, apply_edits
        from formatter_modules.formatter_protection import protected_spans
        source = "SELECT SUM(a) OVER (PARTITION BY 'x,y',b ORDER BY c,d) FROM t;"
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits, handled = nested_query_gap_edits(source, tree, include_simple=True, include_windows=True)
        self.assertEqual(handled, {0})
        self.assertTrue(edits)
        self.assertEqual(len({e.group_id for e in edits}), 1)
        spans = [(p.start,p.end) for p in protected_spans(source)]
        accepted, warnings = plan_edits(source, edits, protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(len(accepted), len(edits))
        reverse, warnings = plan_edits(source, list(reversed(edits)), protected=spans)
        self.assertEqual(warnings, [])
        self.assertEqual(apply_edits(source, accepted), apply_edits(source, reverse))
        e = next(e for e in edits if ',' in source[e.start:e.end])
        accepted, warnings = plan_edits(source, edits, protected=spans+[(e.start,e.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))
        accepted, warnings = plan_edits(source, [Edit(e.start,e.start,' ', 'conflict')]+edits)
        self.assertIn(len([x for x in accepted if x.group_id == e.group_id]), (0,len(edits)))
        self.assertTrue(any(d.code == 'SQLFMT-E001' for d in warnings))

    def test_validator_rejects_window_changes(self):
        from formatter import validate_sql_unchanged
        source = 'SELECT SUM(a) over (partition by b order by c DESC ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS n FROM t;'
        valid = format_sql(source)
        validate_sql_unchanged(source, valid)
        for invalid in (valid.replace('OVER', 'OvEr'),valid.replace('PARTITION', 'Partition'),
                        valid.replace('DESC', 'ASC'), valid.replace('2 PRECEDING', '3 PRECEDING'),
                        valid.replace('ROWS', 'RANGE'), valid.replace('SUM(a)', 'SUM(b)'),
                        valid.replace('AND CURRENT ROW', 'AND 1=1 AND CURRENT ROW')):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_sql_unchanged(source, invalid)

    def test_named_window_runtime_refuses_without_partial_changes(self):
        from formatter import validate_sql_unchanged
        for source in ('SELECT SUM(a) OVER w FROM t;',
                       'SELECT SUM(a) OVER (w ORDER BY b,c) FROM t;'):
            d1,d2=[],[]
            first = format_sql(source, diagnostics=d1)
            self.assertEqual(first, source)
            self.assertEqual(format_sql(first, diagnostics=d2), source)
            validate_sql_unchanged(source, first)
            self.assertEqual([d.code for d in d1], ['SQLFMT-E004'])
            self.assertEqual(d1,d2)

    def test_unsupported_windows_and_qualify_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in ('SELECT SUM(a) OVER w FROM t;',
                       'SELECT SUM(a) OVER (w ORDER BY b) FROM t;',
                       'SELECT a FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY a)=1;'):
            tree = Linter(dialect='teradata').parse_string(source).tree
            self.assertEqual(nested_query_gap_edits(source, tree, include_simple=True,
                include_joins=True, include_cte=True, include_sets=True, include_windows=True), ([],set()))

if __name__ == "__main__":
    unittest.main()
