"""B10.4: derived targets, root margins and AST-proven optional table AS."""
import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_clause_gaps import (
    nested_query_gap_edits, statement_margin_edits, table_alias_gap_edits,
)
from formatter_modules.formatter_edits import Edit, apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans
from dbeaver_adapter import PROFILE_FORMATTERS
from tests.helpers.assertions import assert_protected_spans_preserved
from tests.helpers.fixtures import wrap


class LayoutCorrectionTests(unittest.TestCase):
    def check(self, source, expected=None):
        d1, d2 = [], []
        actual = format_sql(source, diagnostics=d1)
        if expected is not None:
            self.assertEqual(actual, expected)
        self.assertEqual(d1, [])
        self.assertEqual(format_sql(actual, diagnostics=d2), actual)
        self.assertEqual(d2, [])
        validate_sql_unchanged(source, actual)
        assert_protected_spans_preserved(self, source, actual)
        return actual

    def test_exact_derived_join_and_existing_on_alignment(self):
        self.check('SELECT a.id FROM t a LEFT JOIN (SELECT b.id FROM u b)cbm ON a.id=cbm.id;',
                   'SELECT\n    a.id\nFROM t a\n\nLEFT JOIN (\n    SELECT\n        b.id\n    FROM u b\n) cbm\nON a.id = cbm.id\n;\n')

    def test_join_kinds_and_cross_join(self):
        for kind in ('INNER JOIN', 'RIGHT JOIN', 'FULL OUTER JOIN', 'CROSS JOIN'):
            with self.subTest(kind=kind):
                tail = '' if kind == 'CROSS JOIN' else ' ON a.id=b.id AND b.id>0'
                actual = self.check('SELECT a.id FROM t a '+kind+' (SELECT id FROM u) AS b'+tail+';')
                self.assertIn(kind+' (\n    SELECT\n        id\n    FROM u\n) b', actual)
                if tail:
                    self.assertIn('\nON a.id = b.id\n    AND b.id > 0', actual)
                else:
                    self.assertNotIn('\nON ', actual)

    def test_derived_from_alias_gap(self):
        for gap in ('', '   ', '\n', ' AS ', ' as '):
            with self.subTest(gap=gap):
                self.check('SELECT x FROM (SELECT x FROM t)'+gap+'q;',
                           'SELECT\n    x\nFROM (\n    SELECT\n        x\n    FROM t\n) q\n;\n')

    def test_nested_and_consecutive_joins(self):
        s='SELECT a.id FROM t a LEFT JOIN (SELECT b.id FROM u b JOIN (SELECT id FROM v) c ON b.id=c.id) x ON a.id=x.id JOIN (SELECT id FROM w) y ON a.id=y.id;'
        a=self.check(s)
        self.assertIn('    JOIN (\n        SELECT\n            id\n        FROM v\n    ) c\n    ON b.id = c.id', a)
        self.assertIn('\nJOIN (\n    SELECT', a)
        self.assertIn('\n) y\nON a.id = y.id', a)

    def test_cte_insert_and_procedural_dml(self):
        join='SELECT a.id FROM t AS a LEFT JOIN (SELECT id FROM u AS b) AS c ON a.id=c.id'
        for s in ('WITH x AS ('+join+') SELECT id FROM x;', 'INSERT INTO v '+join+';',
                  wrap('INSERT INTO v '+join+'; DELETE FROM t AS a WHERE a.id=1;')):
            with self.subTest(source=s):
                a=self.check(s)
                self.assertNotIn('AS a', a)
                self.assertNotIn('AS c', a)
                if s.startswith('CREATE'):
                    self.assertIn('    LEFT JOIN (\n        SELECT', a)
                    self.assertIn('\n    ON a.id = c.id', a)

    def test_comments_by_derived_brackets_remain_attached(self):
        for s in ('SELECT a.id FROM t a LEFT JOIN ( -- open\nSELECT id FROM u\n/* close */) c ON a.id=c.id;',
                  'SELECT a.id FROM t a LEFT JOIN /* target */ (SELECT id FROM u) /* alias */ c ON a.id=c.id;',
                  'SELECT a.id FROM t a LEFT JOIN (SELECT id FROM u /* close */) AS c -- alias\nON a.id=c.id;'):
            with self.subTest(source=s):
                a=self.check(s)
                self.assertIn('/*',a)
                self.assertIn('\nON ',a)

    def test_table_as_only_and_mixed_case(self):
        for keyword in ('AS','as','As','aS'):
            with self.subTest(keyword=keyword):
                self.check(f'SELECT CAST(a.id AS INTEGER) AS x FROM t {keyword} a JOIN u {keyword} b ON a.id=b.id;',
                           'SELECT\n    CAST(a.id AS INTEGER) AS x\nFROM t a\n\nJOIN u b\nON a.id = b.id\n;\n')

    def test_multiple_tables_and_quoted_identifiers(self):
        a=self.check('SELECT a.id AS x, b.id FROM "Table AS" AS a, u AS b JOIN "Other" AS "Alias AS" ON b.id="Alias AS".id;')
        self.assertIn('FROM "Table AS" a', a)
        self.assertIn('JOIN "Other" "Alias AS"', a)
        self.assertIn('a.id AS x', a)

    def test_as_comments_are_conservative(self):
        for gap in (' /* before */ AS ', ' AS /* after */ ', ' AS -- alias\n'):
            with self.subTest(gap=gap):
                source='SELECT a.id FROM t'+gap+'a;'
                a=self.check(source)
                self.assertIn('AS',a)
                tree=source_linter().parse_string(source).tree
                self.assertEqual(table_alias_gap_edits(source,tree),[])

    def test_functions_literals_cast_and_aliases_are_not_table_keywords(self):
        s="SELECT COALESCE(a,1) AS x, CAST(a AS VARCHAR(10)) AS y, 'AS )q JOIN (' AS z FROM t AS a WHERE a IN (1,2);"
        a=self.check(s)
        self.assertIn("'AS )q JOIN (' AS z",a)
        self.assertIn('COALESCE(a,1) AS x',a)
        self.assertIn('CAST(a AS VARCHAR(10)) AS y',a)

    def test_zero_margin_for_root_statement_kinds(self):
        for s in ('SELECT a FROM t;', 'WITH x AS (SELECT a FROM t) SELECT a FROM x;',
                  'INSERT INTO t SELECT a FROM u;', 'UPDATE t SET a=1;', 'DELETE FROM t WHERE a=1;'):
            with self.subTest(sql=s):
                a=self.check(' \t  '+s)
                self.assertTrue(a.startswith(s.split()[0]))

    def test_multiple_statements_and_blank_lines(self):
        a=self.check('    SELECT a FROM t;\n\n    UPDATE t SET a=1;\n\n\n    DELETE FROM t WHERE a=1;')
        self.assertIn(';\n\nUPDATE',a)
        self.assertIn(';\n\n\nDELETE',a)
        b=self.check('    SELECT a FROM t;    UPDATE t SET a=1;')
        self.assertIn(';\nUPDATE',b)

    def test_root_comments_and_multiline_protected_content(self):
        s='/* head\n    keep */\n    SELECT \'x\n    y\' AS "a\nb" FROM t;'
        a=self.check(s)
        self.assertIn('*/\nSELECT',a)

    def test_same_line_leading_block_comment_keeps_bytes_and_zero_column(self):
        for source in ('/* lead */    UPDATE t SET a=1;',
                       '/* multi\n  line */    SELECT a FROM t;',
                       'SELECT a FROM t; /* previous */    UPDATE t SET a=1;'):
            with self.subTest(source=source):
                a=self.check(source)
                self.assertIn('*/\n'+('SELECT' if 'multi' in source else 'UPDATE'),a)

    def test_endings_bom_profiles_and_repeated_calls(self):
        s='    SELECT a.id FROM t AS a\nLEFT JOIN (SELECT id FROM u) AS b ON a.id=b.id;'
        for ending in ('\n','\r\n','\r','\r\n\n\r'):
            source=s.replace('\n',ending)
            self.check(source)
            for bom in (b'',b'\xef\xbb\xbf'):
                raw=bom+source.encode()
                outputs=[]
                for profile in PROFILE_FORMATTERS.values():
                    a=profile(raw)
                    self.assertNotEqual(a,raw)
                    self.assertEqual(profile(a),a)
                    self.assertTrue(a.startswith(b'SELECT'))
                    outputs.append(a)
                self.assertEqual(*outputs)

    def test_procedure_margin_and_protected_endings(self):
        source='\ufeff'+wrap("WHILE a<2 DO INSERT INTO t SELECT 'x\r\ny' AS x FROM u AS b; SET a=a+1; END WHILE;")
        a=self.check(source)
        self.assertTrue(a.startswith('\ufeffCREATE'))
        self.assertIn('\n        INSERT',a)
        self.assertIn('\n        FROM u b',a)

    def test_alias_and_margin_planner_conflicts_remain_atomic(self):
        source='    SELECT a.id FROM t AS a;'
        tree=source_linter().parse_string(source).tree
        candidates=table_alias_gap_edits(source,tree)
        self.assertEqual(len(candidates),1)
        edit=candidates[0]
        for protected,other in (([(edit.start,edit.end)],[]),
                                ([],[Edit(edit.start,edit.start,'x','conflict')])):
            accepted,ds=plan_edits(source,candidates+other,protected)
            self.assertFalse(any(e.group_id==edit.group_id for e in accepted))
            self.assertTrue(ds)
        margins=statement_margin_edits(source,tree)
        self.assertEqual(apply_edits(source,margins),'SELECT a.id FROM t AS a;')

    def test_derived_layout_and_alias_edits_respect_atomic_planner(self):
        source='SELECT a.id FROM t a JOIN (SELECT id FROM u) b ON a.id=b.id;'
        tree=source_linter().parse_string(source).tree
        edits, owners=nested_query_gap_edits(source,tree,include_simple=True,include_joins=True)
        self.assertEqual(owners,{0})
        self.assertEqual(len({e.group_id for e in edits}),1)
        accepted,ds=plan_edits(source,edits)
        reverse,reverse_ds=plan_edits(source,list(reversed(edits)))
        self.assertEqual(ds+reverse_ds,[])
        self.assertEqual(apply_edits(source,accepted),apply_edits(source,reverse))
        edit=next(e for e in edits if e.start<e.end)
        blocked,ds=plan_edits(source,edits,[(edit.start,edit.end)])
        self.assertEqual(blocked,[])
        self.assertTrue(any(d.code=='SQLFMT-E002' for d in ds))

        # B10.4 enables derived targets, not unrelated formerly opaque forms.
        for opaque in ('SELECT a FROM t CROSS JOIN u;',
                       'SELECT id FROM t WHERE id IN (SELECT a.id FROM a JOIN b ON a.id=b.id);'):
            tree=source_linter().parse_string(opaque).tree
            self.assertEqual(nested_query_gap_edits(opaque,tree,include_simple=True,
                                                    include_joins=True),([],set()))

    def test_ambiguous_comments_and_procedural_conflict_refuse_safely(self):
        source='SELECT a.id FROM t a JOIN (SELECT id FROM u)\n-- alias\n\nAS b ON a.id=b.id;'
        ds=[];actual=format_sql(source,diagnostics=ds)
        self.assertIn('SQLFMT-C001',[d.code for d in ds])
        self.assertIn('AS b',actual)
        validate_sql_unchanged(source,actual)
        assert_protected_spans_preserved(self,source,actual)
        self.assertEqual(format_sql(actual,diagnostics=[]),actual)
        from formatter_modules.formatter_edits import Diagnostic
        raw=wrap('INSERT INTO t SELECT x FROM u AS a;')
        with patch('formatter_modules.formatter_procedure.plan_edits',
                   return_value=([],[Diagnostic('SQLFMT-E001',1,'injected')])):
            ds=[]
            self.assertEqual(format_sql(raw,diagnostics=ds),raw)
            self.assertIn('SQLFMT-E001',[d.code for d in ds])

    def test_quoted_alias_protected_bytes_and_function_target(self):
        source='SELECT "a\r\nb".id AS "AS" FROM "t\rname" AS "a\r\nb";'
        a=self.check(source)
        self.assertIn('FROM "t\rname" "a\r\nb"',a)
        self.assertIn('AS "AS"',a)
        source='SELECT * FROM TABLE(fn()) AS a;'
        parsed=source_linter().parse_string(source)
        if not parsed.violations:
            self.assertEqual(table_alias_gap_edits(source,parsed.tree),[])
            with self.assertRaises(ValueError):
                validate_sql_unchanged(source,source.replace(' AS ', ' '))

    def test_unsupported_alias_shape_is_opaque(self):
        # Alias column lists are outside the proven two-part alias grammar.
        s='SELECT a.x FROM (SELECT x FROM t) AS a(x);'
        parsed=source_linter().parse_string(s)
        if not parsed.violations:
            self.assertEqual(table_alias_gap_edits(s,parsed.tree),[])
        # Never grant token deletion for an unsupported/ambiguous form.
        with self.assertRaises(ValueError):
            validate_sql_unchanged(s,s.replace(' AS ', ' '))


class TableAliasValidatorTests(unittest.TestCase):
    def test_only_original_ast_table_as_may_be_deleted(self):
        s='SELECT a.id AS x FROM t AS a JOIN u AS b ON a.id=b.id WHERE a.id>0 AND b.id>0;'
        candidate=s.replace('t AS a','t a').replace('u AS b','u b')
        validate_sql_unchanged(s,candidate)
        validate_sql_unchanged(s,candidate.replace('WHERE ', 'WHERE 1=1 AND '))
        for invalid in (candidate.replace('id AS x','id x'),candidate.replace('t a','t z'),
                        candidate.replace('a.id=b.id','b.id=a.id'),candidate.replace('JOIN','LEFT JOIN'),
                        candidate.replace('u b','u AS AS b')):
            with self.subTest(candidate=invalid),self.assertRaises(ValueError):
                validate_sql_unchanged(s,invalid)

    def test_no_as_insertion_or_deletion_in_other_contexts(self):
        pairs=[('SELECT a FROM t b;', 'SELECT a FROM t AS b;'),
               ('SELECT CAST(a AS INTEGER) FROM t;', 'SELECT CAST(a INTEGER) FROM t;'),
               ("SELECT 'AS' FROM t AS b;", "SELECT '' FROM t b;"),
               ('SELECT a FROM t /* keep */ AS b;', 'SELECT a FROM t /* keep */ b;'),
               ('WITH a AS (SELECT x FROM t) SELECT x FROM a;', 'WITH a (SELECT x FROM t) SELECT x FROM a;')]
        for source,candidate in pairs:
            with self.subTest(source=source),self.assertRaises(ValueError):
                validate_sql_unchanged(source,candidate)
