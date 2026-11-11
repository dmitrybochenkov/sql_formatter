"""Public synthetic scalar lists; Corporate compatibility is checked separately."""
import pytest
from unittest.mock import patch
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_config import validate, use_settings, ConfigurationError
from formatter_modules.formatter_protection import protected_spans
from formatter_modules.parenthesized_lists import format_parenthesized_lists

MODES = ('single_line', 'multiline', 'adaptive')


def settings(mode, limit=40):
    return validate({'schema_version':1, 'layout':{'parenthesized_lists':{'mode':mode,'max_line_length':limit}}})


def check(source, mode, limit=40):
    with use_settings(settings(mode,limit)):
        ds=[]
        actual=format_sql(source,diagnostics=ds)
        assert format_sql(actual,diagnostics=[]) == actual
        validate_sql_unchanged(source,actual)
        assert [(p.kind,source[p.start:p.end]) for p in protected_spans(source)] == [(p.kind,actual[p.start:p.end]) for p in protected_spans(actual)]
        assert not any(d.code.startswith('SQLFMT-E') for d in ds)
        return actual


@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('source',[
    'SELECT a FROM t WHERE a IN (1,2,3);',
    "SELECT a FROM t WHERE a NOT IN ('ACTIVE','BLOCKED','PENDING','SUSPENDED','CLOSED');",
    "INSERT INTO t VALUES (1,'x'),(2,'y');",
    "SELECT a FROM t WHERE a IN (COALESCE(1,2),CAST(3 AS INTEGER),NULL,CASE WHEN a=1 THEN 2 ELSE 3 END);",
    "SELECT a FROM t WHERE a IN ('a,b','it''s fine',:Bind);",
    'SELECT a FROM t WHERE a IN (SELECT a FROM u WHERE b IN (1,2,3));',
    'SELECT a FROM t WHERE a IN (1, -- attached\n2,3);',
    'SELECT a FROM t WHERE a IN (1,\n-- leading\n/* second */\n2,3);',
    'SELECT a FROM t WHERE a IN (1,\n/* multi\nline */\n2,3);',
    'SELECT a FROM t WHERE a IN (1,\n-- ambiguous\n\n2,3);',
    'SELECT a FROM t WHERE a IN (1 /* trailing */,\n-- leading\n2);',
    'WITH c AS (SELECT a FROM t WHERE a IN (1,2)) SELECT a FROM c WHERE a IN (3,4);',
    'CREATE PROCEDURE p() BEGIN DELETE FROM t WHERE a IN (1,2,3); END;',
])
def test_matrix(source,mode):
    check(source,mode)


@pytest.mark.parametrize('mode',MODES)
@pytest.mark.parametrize('ending',['\n','\r\n','\r'])
def test_protected_line_endings(mode,ending):
    check("SELECT a FROM t WHERE a IN ('first"+ending+"second', /* first"+ending+"second */ 2);",mode)


def test_exact_modes_and_prefix_limit():
    source="SELECT a FROM t WHERE a IN ('AAAA','BBBB','CCCC','DDDD');"
    assert "IN ('AAAA', 'BBBB', 'CCCC', 'DDDD')" in check(source,'single_line',20)
    assert "IN (\n    'AAAA'\n    , 'BBBB'\n    , 'CCCC'\n    , 'DDDD'\n)" in check(source,'multiline')
    actual=check(source,'adaptive',24)
    assert "IN (\n    'AAAA', 'BBBB'\n    , 'CCCC', 'DDDD'\n)" in actual
    assert all(len(line)<=24 for line in actual.splitlines())
    assert 'IN (1, 2)' in check('SELECT a FROM t WHERE a IN (1,2);','adaptive',24)
    assert 'IN (\n' in check('SELECT a FROM t WHERE very_long_column IN (1,2);','adaptive',24)


def test_oversize_item_and_other_brackets():
    literal="'"+'x'*80+"'"
    actual=check(f'SELECT COALESCE(a,b), CAST(a AS DECIMAL(10,2)) FROM t WHERE a IN ({literal},2);','adaptive',20)
    assert literal in actual
    assert 'COALESCE(a,b)' in actual and 'DECIMAL(10,2)' in actual


def test_planner_protected_conflict_rejects_entire_list():
    from formatter_modules.formatter_protection import ProtectedSpan
    source='SELECT a FROM t WHERE a IN (1,2);'
    with use_settings(settings('multiline')), patch('formatter_modules.parenthesized_lists.protected_spans',return_value=[ProtectedSpan(source.index(',') ,source.index(',')+1,'block_comment')]):
        result,ds=format_parenthesized_lists(source)
    # Synthetic protection over a separator is never edited partially.
    assert result==source


@pytest.mark.parametrize('value',[0,19,1001,True,1.2,'100'])
def test_invalid_limit(value):
    with pytest.raises(ConfigurationError): settings('adaptive',value)


@pytest.mark.parametrize('value',['legacy','',None,True])
def test_invalid_mode(value):
    with pytest.raises(ConfigurationError): settings(value)


def test_absence_is_compatibility_fallback():
    source='SELECT a FROM t WHERE a IN (1,2);'
    assert format_parenthesized_lists(source)==(source,[])


def test_actual_protected_span_rejects_all_planned_gaps():
    from formatter_modules.formatter_protection import ProtectedSpan
    source='SELECT a FROM t WHERE a IN (1,2);'
    with use_settings(settings('multiline')), patch('formatter_modules.parenthesized_lists.protected_spans',return_value=[ProtectedSpan(source.index(','),source.index(',')+1,'string')]):
        result,ds=format_parenthesized_lists(source)
    assert result==source
    assert [d.code for d in ds]==['SQLFMT-E002']


def test_conflicting_insertion_does_not_partially_apply_list():
    from formatter_modules.formatter_edits import plan_edits,Edit
    source='SELECT a FROM t WHERE a IN (1,2);'
    pos=source.index('(')+1
    def conflict(text,edits,**kwargs):
        return plan_edits(text,[Edit(pos,pos,' ','OTHER')]+edits,**kwargs)
    with use_settings(settings('multiline')), patch('formatter_modules.parenthesized_lists.plan_edits',side_effect=conflict):
        from formatter_modules.parenthesized_lists import _format_once
        result,ds=_format_once(source)
    assert result==source[:pos]+' '+source[pos:]
    assert [d.code for d in ds]==['SQLFMT-E001']


def test_adaptive_accounts_for_suffix_and_procedural_indent():
    source='SELECT a FROM t WHERE a IN (1,2,3) OR b IN (4,5,6);'
    actual=check(source,'adaptive',24)
    assert all(len(line)<=24 for line in actual.splitlines())
    source="CREATE PROCEDURE p() BEGIN BEGIN DELETE FROM t WHERE a IN ('AAAA','BBBB','CCCC','DDDD'); END; END;"
    actual=check(source,'adaptive',24)
    assert all(len(line)<=24 for line in actual.splitlines())
    check('INSERT INTO t VALUES (1,2,3),(4,5,6),(7,8,9);','adaptive',24)


def test_bad_nested_schema_and_effective_settings():
    from formatter_modules.corporate_profile import CORPORATE
    from formatter_modules.formatter_config import differences
    for layout in ([],{'other':{}},{'parenthesized_lists':[]},{'parenthesized_lists':{'other':1}}):
        with pytest.raises(ConfigurationError): validate({'schema_version':1,'layout':layout})
    assert not differences(validate({'schema_version':1,'layout':{'parenthesized_lists':{'max_line_length':60}}}),CORPORATE)
    assert settings('single_line',20)==settings('single_line',1000)
    assert differences(settings('adaptive'),CORPORATE)
