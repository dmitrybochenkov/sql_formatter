"""Synthetic objects only, preserving the reported Unicode alias spelling."""
import pytest
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_config import validate,use_settings
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_protection import protected_spans
from dbeaver_adapter import format_bytes

SAMPLE = '''SELECT reg.region_name, reg.branch_id, reg.branch_name, reg.zone_id,
COUNT(src.id) AS Количествво_ИНН
FROM sample_data.events src
INNER JOIN sample_data.revenue rev ON rev.id=src.id AND rev.branch_id=src.branch_id AND rev.amount=src.amount
LEFT JOIN sample_data.regions reg ON reg.branch_id=src.branch_id
GROUP BY 1,2,3,4;'''

@pytest.mark.parametrize('source',[
    SAMPLE,
    'SELECT COUNT(a) AS "Количество_ИНН" FROM t;',
    'SELECT Смешанный_ID, 日本語 FROM Таблица;',
    'SELECT :Bind AS Алиас FROM t;',
    'SELECT МояФункция(a) AS Результат FROM t;',
    "SELECT 'Привет, SELECT', a AS Количество FROM t /* Комментарий */;",
    'WITH Источник AS (SELECT id AS Номер FROM t) SELECT Номер FROM Источник;',
    'CREATE PROCEDURE p() BEGIN INSERT INTO Выход SELECT id AS Номер FROM Вход; END;',
])
@pytest.mark.parametrize('policy',['lower','upper','preserve'])
def test_unicode_preserved(source,policy):
    with use_settings(validate({'schema_version':1,'case':{'identifiers':policy}})):
        ds=[]; actual=format_sql(source,diagnostics=ds)
        assert not ds
        assert format_sql(actual,diagnostics=[])==actual
        validate_sql_unchanged(source,actual)
        assert not source_linter().parse_string(actual).violations
        def unicode_leaves(text):
            def walk(n):
                if not n.segments and n.is_type('naked_identifier', 'function_name_identifier'): yield n.raw
                for c in n.segments: yield from walk(c)
            return [t for t in walk(source_linter().parse_string(text).tree) if not t.isascii()]
        assert unicode_leaves(source)==unicode_leaves(actual)
        assert [(p.kind,source[p.start:p.end]) for p in protected_spans(source)]==[(p.kind,actual[p.start:p.end]) for p in protected_spans(actual)]


def test_validator_rejects_unicode_case_or_spelling_changes():
    source='SELECT a AS Алиас FROM t;'
    for changed in ['SELECT a AS алиас FROM t;','SELECT a AS Иное FROM t;']:
        with pytest.raises(ValueError): validate_sql_unchanged(source,changed)


@pytest.mark.parametrize('source',['SELECT a AS 💥 FROM t;', 'SELECT a AS Имя- FROM t;'])
def test_invalid_unicode_is_atomic(source):
    raw=source.encode()
    assert format_bytes(raw)==raw


@pytest.mark.parametrize('name',['Име\u0301на','a\u00b7b','Ⅳ_номер','€Имя','İ','ı','K','Straße'])
def test_identifier_categories_and_no_unicode_normalization(name):
    source=f'SELECT a AS {name} FROM t;'
    actual=format_sql(source,diagnostics=[])
    assert name in actual
    assert format_sql(actual,diagnostics=[])==actual
    validate_sql_unchanged(source,actual)


@pytest.mark.parametrize('name',['²Имя','\u0301Имя'])
def test_invalid_identifier_start(name):
    raw=f'SELECT a AS {name} FROM t;'.encode()
    assert format_bytes(raw)==raw
