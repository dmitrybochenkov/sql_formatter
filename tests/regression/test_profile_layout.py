import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_config import validate, use_settings, PERSONAL_DEFAULTS
from formatter_modules.formatter_protection import protected_spans


class ProfileLayoutTests(unittest.TestCase):
    def check(self, source, options, fragments=()):
        with use_settings(validate({'schema_version':1,**options})):
            ds=[];one=format_sql(source,diagnostics=ds)
            self.assertNotEqual(one,source)
            self.assertFalse({d.code for d in ds}&{'SQLFMT-E001','SQLFMT-E002','SQLFMT-E003','SQLFMT-E004'})
            two=format_sql(one,diagnostics=[])
            self.assertEqual(one,two)
            validate_sql_unchanged(source,one)
            spans=lambda sql:[(s.kind,sql[s.start:s.end]) for s in protected_spans(sql)]
            self.assertEqual(spans(source),spans(one))
            for fragment in fragments:self.assertIn(fragment,one)
            return one

    def test_all_case_policies_real_cp_tokens(self):
        source='sEleCt SuM(Amount), CaSt(ID aS InTeGeR), nUlL, "Quoted" FROM Table_Name;'
        for mode in ('upper','lower','preserve'):
            values={'case':dict.fromkeys(PERSONAL_DEFAULTS['case'],mode)}
            out=self.check(source,values)
            expected={'upper':['SELECT','SUM(AMOUNT)','INTEGER','NULL','TABLE_NAME'],
                      'lower':['select','sum(amount)','integer','null','table_name'],
                      'preserve':['sEleCt','SuM(Amount)','InTeGeR','nUlL','Table_Name']}[mode]
            for fragment in expected:self.assertIn(fragment,out)

    def test_each_comma_setting_independent(self):
        source='SELECT a,b FROM t,u GROUP BY a,b ORDER BY a DESC,b NULLS LAST;'
        fragments={'select':'    a,\n    b','from':'FROM t,\n    u',
                   'group_by':'GROUP BY\n    a,\n    b','order_by':'ORDER BY\n    a DESC,\n    b NULLS LAST'}
        for name, fragment in fragments.items():
            with self.subTest(name=name):self.check(source,{'commas':{name:'trailing'}},[fragment])

    def test_multiline_single_element_exception(self):
        for source in ('SELECT a FROM t GROUP BY a;','SELECT a FROM t GROUP BY\n a;'):
            self.check(source,{},['GROUP BY a\n'])
        self.check('SELECT a,b FROM t GROUP BY a,b;',{},['GROUP BY\n    a\n    , b'])

    def test_group_inline_preserve_breaks_and_commas(self):
        source='SELECT a,b,c FROM t GROUP BY a,b,\n c;'
        self.check(source,{'group_by':{'layout':'inline'}},['GROUP BY a, b, c'])
        for style,fragment in [('leading','GROUP BY a, b\n    , c'),('trailing','GROUP BY a, b,\n    c')]:
            self.check(source,{'group_by':{'layout':'preserve'},'commas':{'group_by':style}},[fragment])
        self.check('SELECT a FROM t GROUP BY\n a;',{'group_by':{'layout':'preserve'}},['GROUP BY\n    a'])

    def test_spacing_all_boundaries_except_window_order(self):
        source='SELECT a.id,SUM(b.x) FROM t a JOIN u b ON a.id=b.id WHERE a.id>0 GROUP BY a.id HAVING SUM(b.x)>0 QUALIFY ROW_NUMBER() OVER (ORDER BY a.id)=1 ORDER BY a.id;'
        none=self.check(source,{'spacing':{'blank_line_before':[]}})
        for title in ('JOIN','WHERE','GROUP BY','HAVING','QUALIFY','ORDER BY'):
            self.assertNotIn('\n\n'+title,none)
        for name,title in [('from','FROM'),('join','JOIN'),('where','WHERE'),('group_by','GROUP BY'),('having','HAVING'),('qualify','QUALIFY'),('order_by','ORDER BY')]:
            self.check(source,{'spacing':{'blank_line_before':[name]}},['\n\n'+title])
        self.assertIn('OVER (\n    ORDER BY a.id',none)

    def test_where_false_nested_scopes_existing_prefix_and_having(self):
        source='SELECT a FROM t WHERE a IN (SELECT b FROM u WHERE b>0 AND b<5) AND a>1 GROUP BY a HAVING COUNT(*)>1 AND SUM(a)>2;'
        out=self.check(source,{'where':{'insert_1_equals_1':False}})
        self.assertNotIn('WHERE 1=1',out);self.assertIn('HAVING 1=1',out)
        self.check('SELECT a FROM t WHERE 1=1 AND a>0;',{'where':{'insert_1_equals_1':False}},['WHERE 1=1'])
        for predicate in ('a BETWEEN 1 AND 3','a=1 OR a=2','(a=1 AND b=2)'):
            out=self.check('SELECT a FROM t WHERE '+predicate+';',{})
            self.assertNotIn('WHERE 1=1',out)

    def test_trailing_comments_expressions_and_protected_newlines(self):
        sources=["SELECT COALESCE(a,b), 'x,y', c FROM t GROUP BY COALESCE(a,b), c ORDER BY c DESC, a;",
                 'SELECT a, -- note\n b FROM t GROUP BY a, -- note\n b ORDER BY a, /* block\r\ncontent */ b;',
                 'SELECT a,\n-- one\n/* two */\nb FROM t GROUP BY a,\n-- first\n/* second */\nb;']
        options={'commas':dict.fromkeys(('select','from','group_by','order_by'),'trailing')}
        for source in sources:
            with self.subTest(source=source):self.check(source,options)
        self.check(sources[1],{'group_by':{'layout':'inline'}})

    def test_cte_derived_sets_procedure_and_endings(self):
        sources=['WITH c AS (SELECT a,b FROM t GROUP BY a,b) SELECT a,b FROM c UNION ALL SELECT a,b FROM u;',
                 'SELECT a.id,b.x FROM t a LEFT JOIN (SELECT id,x FROM u) b ON a.id=b.id WHERE a.id>0 AND b.x>1;',
                 'CREATE PROCEDURE p() BEGIN INSERT INTO t SELECT a,b FROM u WHERE a>0 AND b>0 GROUP BY a,b; DELETE FROM u WHERE a=1 AND b=2; END;']
        options={'case':{'keywords':'lower'},'commas':{'select':'trailing'},'group_by':{'layout':'inline'},'where':{'insert_1_equals_1':False}}
        for source in sources:
            for ending in ('\n','\r\n','\r'):
                with self.subTest(source=source,ending=repr(ending)):
                    self.check(source.replace(' FROM ',ending+'FROM ')+ending,options)
        self.check("SELECT 'x\r\ny' AS a, \"Q\rR\" FROM t;",options)

    def test_strict_validation_in_each_case_policy(self):
        for mode in ('upper','lower','preserve'):
            with use_settings(validate({'schema_version':1,'case':dict.fromkeys(PERSONAL_DEFAULTS['case'],mode)})):
                for bad in ("SELECT 'y' FROM t;", "SELECT 'x' FROM u;", "SELECT 'x' FROM t WHERE 1=1;"):
                    with self.assertRaises(ValueError):validate_sql_unchanged("SELECT 'x' FROM t;",bad)
        with use_settings(validate({'schema_version':1,'case':{'keywords':'preserve'}})):
            with self.assertRaises(ValueError):validate_sql_unchanged('select a from t;','SELECT a FROM t;')

    def test_ambiguous_list_is_not_partially_edited(self):
        source='SELECT a FROM t GROUP BY a,\n-- detached\n\nb;'
        with use_settings(validate({'schema_version':1,'commas':{'group_by':'trailing'}})):
            ds=[];out=format_sql(source,diagnostics=ds)
            self.assertTrue(any(d.code=='SQLFMT-C001' for d in ds))
            self.assertIn('GROUP BY a,\n-- detached\n\nb',out)
            self.assertEqual(out,format_sql(out,diagnostics=[]))

    def test_profile_list_edits_reject_as_an_atomic_group(self):
        from formatter_modules import profile_layout as module
        from formatter_modules.formatter_edits import plan_edits as planner
        source='SELECT\n    a\n    , b\nFROM t\n;\n'
        observed=[]
        def conflict(sql,edits,protected):
            observed.extend(edits)
            first=edits[0]
            return planner(sql,edits,protected=[*protected,(first.start,first.end)])
        with use_settings(validate({'schema_version':1,'commas':{'select':'trailing'}})),patch.object(module,'plan_edits',side_effect=conflict):
            output,warnings=module.apply_profile_layout(source,source)
        self.assertTrue(observed);self.assertEqual(output,source)
        self.assertIn('SQLFMT-E002',[d.code for d in warnings])

    def test_where_disabled_rejects_new_prefix_in_validator(self):
        with use_settings(validate({'schema_version':1,'where':{'insert_1_equals_1':False}})):
            with self.assertRaises(ValueError):
                validate_sql_unchanged('SELECT a FROM t WHERE a>0 AND b>0;',
                                       'SELECT a FROM t WHERE 1=1 AND a>0 AND b>0;')

    def test_inline_comment_continuation_uses_nested_ast_indent(self):
        source='WITH c AS (SELECT a,b FROM u GROUP BY a, -- group\n b) SELECT a FROM c;'
        self.check(source,{'group_by':{'layout':'inline'}},['    GROUP BY a, -- group\n        b'])
