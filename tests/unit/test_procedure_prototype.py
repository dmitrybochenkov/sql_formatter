"""Parser-only B10.1 tests; no opt-in from any production entry point."""
import unittest
from unittest.mock import patch

from prototypes.teradata_procedures import parse_procedure, prototype_config
from formatter_modules.formatter_runtime import source_linter
from formatter_modules.formatter_case import normalize_case
from formatter import format_sql
from dbeaver_adapter import PROFILE_FORMATTERS


SYNTHETIC = """REPLACE PROCEDURE example_proc(IN p_start_date DATE, OUT p_count INTEGER)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_cur_date DATE;
    DECLARE v_end_date DATE;
    DECLARE v_count INTEGER DEFAULT 0;
    SET v_cur_date = p_start_date;
    SET v_end_date = p_start_date + 2;
    WHILE v_cur_date <= v_end_date DO
        CALL example_log('Processing; -- DO END', v_cur_date);
        -- Remove previous data
        DELETE FROM example_target WHERE event_date = v_cur_date;
        /* Load current day; END WHILE */
        INSERT INTO example_target
        SELECT a.id, b.name, CASE WHEN c.id IS NULL THEN 'END' ELSE 'DO' END
        FROM example_source a
        INNER JOIN example_other b ON a.id = b.id
        LEFT JOIN example_extra c ON a.id = c.id
        WHERE a.event_date = v_cur_date AND a.status IN (1, 2, 3, 4, 5)
          AND a.id NOT IN (SELECT id FROM example_excluded);
        SET v_cur_date = v_cur_date + 1;
    END WHILE;
    SET p_count = v_count;
END;"""


def wrap(body):
    return 'CREATE PROCEDURE p() BEGIN ' + body + ' END;'


def walk(node):
    yield node
    for child in node.segments:
        yield from walk(child)


class ProcedurePrototypeTests(unittest.TestCase):
    def accepted(self, source):
        parsed = parse_procedure(source)
        self.assertTrue(parsed.complete, parsed.tree.stringify())
        self.assertEqual(parsed.tree.raw, source)
        # Every original character appears once; every leaf has its exact slice.
        leaves = [s for s in walk(parsed.tree) if not s.segments and not s.is_meta]
        self.assertEqual(''.join(s.raw for s in leaves), source)
        for s in leaves:
            self.assertEqual(source[s.pos_marker.source_slice], s.raw)
        return parsed.tree

    def test_complete_synthetic_procedure(self):
        tree = self.accepted(SYNTHETIC)
        for kind, count in [('procedure_definition', 1), ('procedure_block', 1),
                            ('procedure_parameter', 2), ('procedure_security', 1),
                            ('procedure_declaration', 3), ('procedure_assignment', 4),
                            ('procedure_while', 1), ('procedure_call', 1),
                            ('delete_statement', 1), ('insert_statement', 1),
                            ('join_clause', 2)]:
            self.assertEqual(len(list(tree.recursive_crawl(kind))), count, kind)
        loop = next(tree.recursive_crawl('procedure_while'))
        self.assertEqual(len(list(loop.recursive_crawl('insert_statement'))), 1)
        self.assertEqual(len(list(loop.recursive_crawl('delete_statement'))), 1)
        self.assertEqual(len(list(loop.recursive_crawl('procedure_assignment'))), 1)

    def test_headers_and_parameters(self):
        for verb in ('CREATE', 'REPLACE', 'create', 'replace'):
            for params in ('', 'p DATE', 'IN p DATE, OUT q DECIMAL(12,2), INOUT r VARCHAR(100)', '"p name" INTEGER'):
                with self.subTest(verb=verb, params=params):
                    self.accepted(f'{verb} PROCEDURE db.p({params}) SQL SECURITY INVOKER BEGIN END;')

    def test_declarations_and_assignments(self):
        self.accepted(wrap('DECLARE a, b INTEGER DEFAULT 0; DECLARE d DATE; SET a=1; SET b=(a+2)*3;'))

    def test_calls_and_opaque_literals(self):
        tree = self.accepted(wrap("CALL db.log_p(); CALL db.log_p('END; -- DO', 'it''s; /* */', COALESCE(1,2));"))
        self.assertEqual(len(list(tree.recursive_crawl('procedure_call'))), 2)
        self.assertEqual(len(list(tree.recursive_crawl('statement_terminator'))), 3)

    def test_nested_and_consecutive_loops(self):
        tree = self.accepted(wrap('WHILE a < 2 DO WHILE b < 3 DO SET b=b+1; END WHILE; SET a=a+1; END WHILE; WHILE c < 4 DO SET c=c+1; END WHILE;'))
        outer = next(tree.recursive_crawl('procedure_while'))
        nested = [s for s in walk(outer) if s.is_type('procedure_while')]
        self.assertEqual(len(nested), 2)
        self.assertEqual(nested[1].raw, 'WHILE b < 3 DO SET b=b+1; END WHILE')
        # Executable wrappers own precisely one terminator, not their parent's END.
        for s in tree.recursive_crawl('procedure_executable'):
            self.assertEqual(s.segments[-1].raw, ';')

    def test_nested_begin_end(self):
        tree = self.accepted(wrap('BEGIN DECLARE x INTEGER; SET x=1; END; SET a=2;'))
        self.assertEqual(len([s for s in walk(tree) if s.is_type('procedure_block')]), 2)

    def test_comments_between_boundaries(self):
        sql = "-- before\n" + wrap("/* declaration */ DECLARE a INTEGER; -- set\nSET a=1; WHILE a < 2 /* DO; */ DO -- call\nCALL p('END WHILE;'); /* next\nstatement */ SET a=a+1; END /* close */ WHILE;") + ' -- after\n'
        self.accepted(sql)

    def test_expressions_and_nested_sql(self):
        self.accepted(wrap("SET d=CAST('2026-01-01' AS DATE); SET t=TIMESTAMP '2026-01-01 00:00:00' + INTERVAL '1' DAY; CALL p(TO_CHAR(d), 'a'||'b'); DELETE FROM t WHERE id IN (1,2) AND (a=1 OR b=2); INSERT INTO t SELECT a FROM u WHERE id IN (SELECT id FROM v);"))

    def test_one_line_and_repeated_parse(self):
        # Strip only indentation/newlines outside line comments for this specimen.
        sql = wrap('SET a=1; WHILE a<3 DO CALL p(a); SET a=a+1; END WHILE;')
        first = self.accepted(sql)
        second = self.accepted(first.raw)
        self.assertEqual(first.stringify(), second.stringify())

    def test_invalid_blocks_delimiters_and_syntax(self):
        invalid = [
            'CREATE PROCEDURE p() BEGIN SET a=1;',
            'CREATE PROCEDURE p() BEGIN SET a=1; END WHILE;',
            wrap('WHILE a<2 DO SET a=a+1; END;'),
            wrap('WHILE a<2 SET a=a+1; END WHILE;'),
            wrap('WHILE a<2 DO WHILE b<2 DO SET b=1; END WHILE;'),
            wrap('SET a=1 SET b=2;'), wrap('CALL p() SET a=1;'),
            wrap('INSERT INTO t SELECT a FROM u SET a=1;'),
            wrap('DELETE FROM t WHERE a=1 SET a=2;'),
            wrap('WHILE a<2 DO CALL p(); END WHILE END;'), wrap('SET a=;'), wrap('CALL p(1,);'),
            wrap('CALL p(1;'), wrap('SET a=1; DECLARE b INTEGER;'),
            wrap('DELETE FROM;'), wrap('INSERT INTO t SELECT FROM;'),
            wrap('DOCALL p();'), wrap("CALL p('unterminated);"),
            'CREATE PROCEDURE p(IN DATE) BEGIN END;',
            'CREATE PROCEDURE p() SQL SECURITY BEGIN END;',
            wrap('SET a=1;')[:-1], wrap('SET a=1;')+' DROP TABLE t;',
        ]
        for sql in invalid:
            with self.subTest(sql=sql):
                parsed = parse_procedure(sql)
                self.assertFalse(parsed.complete)

    def test_unsupported_is_not_raw_fallback(self):
        for body in ('IF a=1 THEN SET a=2; END IF;', 'FOR x AS SELECT a FROM t DO CALL p(); END FOR;', 'label1: WHILE a<1 DO SET a=1; END WHILE label1;', 'DECLARE x CURSOR FOR SELECT a FROM t;', 'UPDATE t SET a=1;', 'SELECT 1;'):
            with self.subTest(body=body):
                self.assertFalse(parse_procedure(wrap(body)).complete)

    def test_execution_tree_and_terminator_ownership(self):
        tree = self.accepted(SYNTHETIC)
        block = next(tree.recursive_crawl('procedure_block'))
        def executable_kinds(node):
            return [next(c.get_type() for c in child.segments if c.is_code)
                    for child in node.segments if child.is_type('procedure_executable')]
        self.assertEqual(executable_kinds(block), [
            'procedure_assignment', 'procedure_assignment', 'procedure_while',
            'procedure_assignment'])
        loop = next(block.recursive_crawl('procedure_while'))
        self.assertEqual(executable_kinds(loop), [
            'procedure_call', 'delete_statement', 'insert_statement',
            'procedure_assignment'])
        self.assertEqual([s.raw for s in loop.segments if s.is_code][-2:], ['END', 'WHILE'])
        self.assertEqual(len(list(tree.recursive_crawl('statement_terminator'))), 12)

    def test_unicode_and_multiline_protected_text(self):
        sql = """DECLARE "имя" VARCHAR(100); SET "имя" = 'строка
END; -- WHILE'; /* блок
DO; */ CALL "журнал"("имя");"""
        self.accepted(wrap(sql))

    def test_prototype_scope_and_version(self):
        with self.assertRaises(ValueError):
            parse_procedure(wrap('SET a=1;')+'\r\n')
        with patch('prototypes.teradata_procedures.sqlfluff.__version__', '0.0'):
            with self.assertRaises(RuntimeError):
                prototype_config()

    def test_runtime_grammar_enabled_profiles_still_fail_closed(self):
        self.accepted(SYNTHETIC)
        baseline = source_linter().parse_string(SYNTHETIC)
        self.assertFalse(list(baseline.tree.recursive_crawl('unparsable')))
        self.assertTrue(parse_procedure(normalize_case(SYNTHETIC)).complete)
        with self.assertRaises(ValueError):
            format_sql(SYNTHETIC)
        original = b'\xef\xbb\xbf' + SYNTHETIC.replace('\n','\r\n').encode()
        with patch('dbeaver_adapter.log_event'):
            for formatter in PROFILE_FORMATTERS.values():
                self.assertEqual(formatter(original), original)


class ExistingDMLReproductionTests(unittest.TestCase):
    """B10.1 defect specimens, upgraded to B10.2a regression assertions."""
    def test_existing_insert_select_non_idempotence(self):
        sql = 'INSERT INTO example_target SELECT a.id, b.name FROM example_source a INNER JOIN example_other b ON a.id = b.id WHERE a.id IN (1, 2);'
        ds1, ds2 = [], []
        first = format_sql(sql, diagnostics=ds1)
        second = format_sql(first, diagnostics=ds2)
        self.assertEqual(first, second)
        self.assertIn('\nSELECT\n    a.id\n    , b.name\nFROM', first)
        self.assertIn('\n\nINNER JOIN', first)
        self.assertEqual(ds1, [])
        self.assertEqual(ds2, [])

    def test_existing_delete_literal_protected_refusal(self):
        sql = "DELETE FROM example_target WHERE id IN (1, 2) AND status = 'OK';"
        ds = []
        actual = format_sql(sql, diagnostics=ds)
        self.assertEqual(actual, "DELETE FROM example_target\n\nWHERE 1=1\n    AND id IN (1, 2)\n    AND status = 'OK'\n;\n")
        self.assertEqual(ds, [])
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)
