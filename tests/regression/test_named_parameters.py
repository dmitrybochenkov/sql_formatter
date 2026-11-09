"""Only synthetic bind names and objects; the original customer SQL is not used."""
from pathlib import Path
import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_protection import protected_spans
from formatter_modules.formatter_config import validate, use_settings
from dbeaver_adapter import format_bytes
from tests.helpers.fixtures import walk

ROOT = Path(__file__).resolve().parents[2]


def binds(source):
    tree = source_linter().parse_string(source).tree
    return [node.raw for node in walk(tree) if node.is_type('named_parameter')]


class NamedParameterTests(unittest.TestCase):
    def check(self, source):
        diagnostics = []
        actual = format_sql(source, diagnostics=diagnostics)
        self.assertNotEqual(actual, source)
        self.assertEqual(diagnostics, [])
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)
        validate_sql_unchanged(source, actual)
        self.assertEqual(binds(source), binds(actual))
        self.assertEqual([(p.kind, source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind, actual[p.start:p.end]) for p in protected_spans(actual)])
        self.assertFalse(any(n.is_type('unparsable') for n in walk(source_linter().parse_string(actual).tree)))
        return actual

    def test_minimal_exact_output(self):
        source = 'select t.report_date,t.id from events t where t.report_date=:Calc_Date and t.id is not null;'
        self.assertEqual(self.check(source), 'SELECT\n    t.report_date\n    , t.id\nFROM events t\n\nWHERE 1=1\n    AND t.report_date = :Calc_Date\n    AND t.id IS NOT NULL\n;\n')

    def test_expression_contexts_functions_repetition_and_case(self):
        sources = [
            'SELECT :Calc_Date, ADD_MONTHS(:Calc_Date,-2), :branch_id FROM events WHERE id=:branch_id;',
            'SELECT CASE WHEN a=:Flag THEN :Yes ELSE :No END v FROM events;',
            'SELECT a.id FROM events a JOIN branches b ON a.id=:JoinId AND b.id=:JoinId WHERE a.id=:Outer;',
            'SELECT a, COUNT(*) FROM events GROUP BY 1 HAVING COUNT(*)>:Min AND SUM(a)>:Limit;',
            'SELECT id FROM events WHERE id IN (:A,:B) AND day BETWEEN :Start AND :End;',
            'SELECT :Select, :_Flag, :a12, :NULL FROM events;',
        ]
        for source in sources:
            with self.subTest(source=source):
                self.check(source)

    def test_cte_nested_set_and_complex_window_query(self):
        simple = 'WITH src AS (SELECT id FROM events WHERE day=:Day) SELECT id FROM src WHERE id IN (SELECT id FROM other WHERE id=:Id) UNION ALL SELECT id FROM archive WHERE day=:Day;'
        self.check(simple)
        complex_sql = (ROOT / 'tests/manual/input.sql').read_text()
        actual = self.check(complex_sql)
        self.assertEqual(binds(actual).count(':Calc_Date'), 2)
        self.assertIn('GROUP BY 1', actual)
        self.assertIn('UNION ALL', actual)
        self.assertIn('PARTITION BY', actual)

    def test_procedure_and_repeated_dml(self):
        self.check('CREATE PROCEDURE p() BEGIN DELETE FROM events WHERE day=:Day; INSERT INTO target SELECT id FROM events WHERE day=:Day; END;')

    def test_protected_text_and_other_colons(self):
        source = 'SELECT \':NotABind\', "X:Id", a::INTEGER FROM events WHERE a=:Id; -- :Ignored\n'
        self.check(source)
        self.assertEqual(binds(source), [':Id'])
        for ending in ('\n', '\r\n', '\r'):
            self.check("SELECT ':One" + ending + ":Two', \"A:B\" FROM events /* :X" + ending + ":Y */ WHERE a=:Mixed_Case;")

    def test_parameter_bytes_not_eligible_for_case_policy(self):
        source = 'select :MiXeD, :MiXeD from events where id=:UPPER;'
        for mode in ('upper', 'lower', 'preserve'):
            with self.subTest(mode=mode), use_settings(validate({'schema_version': 1, 'case': {
                'keywords': mode, 'functions': mode, 'identifiers': mode, 'types': mode, 'literals': mode}})):
                self.check(source)
        for wrong in ('select :mixed, :MiXeD from events where id=:UPPER;',
                      'select :MiXeD, :UPPER from events where id=:MiXeD;'):
            with self.assertRaises(ValueError):
                validate_sql_unchanged(source, wrong)

    def test_unsupported_colons_and_real_parse_errors_rollback(self):
        for source in ('SELECT : FROM events;', 'SELECT :1 FROM events;',
                       'SELECT : name FROM events;', 'SELECT id:Other FROM events;',
                       'SELECT id FROM :TableName;', 'SELECT id FROM events WHERE a=:Id AND ;'):
            with self.subTest(source=source), patch('dbeaver_adapter.log_event'):
                original = b'\xef\xbb\xbf' + source.replace(' FROM', '\r\nFROM').encode()
                self.assertEqual(format_bytes(original), original)

    def test_ast_type_cannot_be_changed_to_identifier(self):
        source = 'SELECT :Mixed FROM events;'
        self.assertEqual(binds(source), [':Mixed'])
        with self.assertRaises(ValueError):
            validate_sql_unchanged(source, 'SELECT Mixed FROM events;')
