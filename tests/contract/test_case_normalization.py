import unittest
from unittest.mock import patch

from dbeaver_adapter import format_bytes
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_case import normalize_case
from formatter_modules.formatter_edits import Diagnostic
from formatter_modules.formatter_protection import protected_spans


class B8CaseTests(unittest.TestCase):
    def check_case(self, source, expected):
        actual = normalize_case(source)
        self.assertEqual(actual, expected)
        self.assertEqual(normalize_case(actual), actual)
        validate_sql_unchanged(source, actual)
        self.assertEqual([(s.kind, source[s.start:s.end]) for s in protected_spans(source)],
                         [(s.kind, actual[s.start:s.end]) for s in protected_spans(actual)])

    def test_all_five_rules_without_layout_changes(self):
        self.check_case("select A.ID, sum(A.N), cast(A.X as varchar(10)), null, true, false\nfrom DB.SCHEMA_TAB A where A.N>0 and A.X is not null;",
                        "SELECT a.id, SUM(a.n), CAST(a.x AS VARCHAR(10)), NULL, TRUE, FALSE\nFROM db.schema_tab a WHERE a.n>0 AND a.x IS NOT NULL;")
        self.check_case('select SUM, sum(AMOUNT) as COUNT from DB.T;',
                        'SELECT sum, SUM(amount) AS count FROM db.t;')

    def test_keywords_cte_join_sets_and_windows(self):
        source = ('with C as (select T.ID from DB.T T left join DB.U U on T.ID=U.ID '
                  'where T.X=1 or U.X=2 group by T.ID having count(*)>1) '
                  'select row_number() over (partition by ID order by ID desc) as RN '
                  'from C qualify RN=1 union all select 1 from C order by RN;')
        expected = ('WITH c AS (SELECT t.id FROM db.t t LEFT JOIN db.u u ON t.id=u.id '
                    'WHERE t.x=1 OR u.x=2 GROUP BY t.id HAVING COUNT(*)>1) '
                    'SELECT ROW_NUMBER() OVER (PARTITION BY id ORDER BY id DESC) AS rn '
                    'FROM c QUALIFY rn=1 UNION ALL SELECT 1 FROM c ORDER BY rn;')
        self.check_case(source, expected)

    def test_protected_content_and_original_offsets(self):
        for ending in ('\n', '\r\n', '\r', '\n\r\n\r'):
            source = f'select{ending}A,\'ACTIVE\r\nSome Text\' as "My\rColumn" /* and\r\nFROM */ from T;'
            expected = f'SELECT{ending}a,\'ACTIVE\r\nSome Text\' AS "My\rColumn" /* and\r\nFROM */ FROM t;'
            self.check_case(source, expected)
            first = format_sql(source, diagnostics=[])
            self.assertEqual(format_sql(first, diagnostics=[]), first)
            validate_sql_unchanged(source, first)

    def test_exact_direction_only(self):
        source = "select A from T where A is null and A='ACTIVE';"
        self.assertEqual(normalize_case(source), "SELECT a FROM t WHERE a IS NULL AND a='ACTIVE';")
        for candidate in (source.replace('A from', 'B from'), source.replace('T where', 'u where'),
                          source.replace("'ACTIVE'", "'active'"), source.replace('and', 'or'),
                          source.replace('null', 'TRUE'), source.replace('A from T', 'T from A')):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                validate_sql_unchanged(source, candidate)
        with self.assertRaises(ValueError):
            validate_sql_unchanged('SELECT a FROM t;', 'SELECT A FROM t;')
        with self.assertRaises(ValueError):
            validate_sql_unchanged('SELECT "X" FROM t;', 'SELECT "x" FROM t;')

    def test_no_case_permission_without_sqlfluff_proposal(self):
        with patch('formatter.normalize_case', side_effect=lambda source: source):
            for source, candidate in (('select a from t;', 'SELECT a from t;'),
                                      ('SELECT A FROM t;', 'SELECT a FROM t;')):
                with self.subTest(source=source), self.assertRaises(ValueError):
                    validate_sql_unchanged(source, candidate)

    def test_full_format_and_adapter(self):
        source = b"select A.ID from DB.T A where A.X=1 and A.Y='ACTIVE';"
        expected = b"SELECT\n    a.id\nFROM db.t a\n\nWHERE 1=1\n    AND a.x = 1\n    AND a.y = 'ACTIVE'\n;\n"
        self.assertEqual(format_bytes(source), expected)
        self.assertEqual(format_bytes(expected), expected)
        refused = b'\xef\xbb\xbfselect sum(A) over W\r\nfrom T;'
        self.assertEqual(format_bytes(refused), refused)

    def test_conflict_rejects_entire_group(self):
        source = 'select A from T;'
        with patch('formatter_modules.formatter_case.plan_edits', return_value=([], [Diagnostic('SQLFMT-E002', 1, 'blocked')])):
            with self.assertRaises(ValueError):
                normalize_case(source)
            self.assertEqual(format_bytes(source.encode()), source.encode())

    def test_comments_cannot_reconfigure_case_rules(self):
        source = '-- sqlfluff:rules:capitalisation.keywords:capitalisation_policy:lower\nselect A from T; -- noqa: CP01,CP02'
        self.check_case(source, source.replace('select A from T;', 'SELECT a FROM t;'))

    def test_ambiguous_unicode_and_unparsable_fail_closed(self):
        # Teradata's qualified UDF name has no CP01–CP05 proposal in 4.4.0.
        # Preserve it instead of guessing classification from its spelling.
        self.check_case('select DB.MyFunc(T.ID) as RESULT from DB.T T;',
                        'SELECT DB.MyFunc(t.id) AS result FROM db.t t;')
        # Lowercasing U+0130 expands to two code points; never guess coordinates.
        for source in ('SELECT İ FROM T;', 'select from;'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                normalize_case(source)
            self.assertEqual(format_bytes(source.encode()), source.encode())
