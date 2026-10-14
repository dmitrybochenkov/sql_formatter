import unittest

from formatter import format_sql

CASES = {
    "simple_select": """
SELECT t.id,t.name
FROM users t
WHERE t.active=1
ORDER BY t.id;
""",
    "joins": """
SELECT t.id,s.amount
FROM users t
INNER JOIN sales s ON t.id=s.user_id AND s.status='OK'
LEFT JOIN regions r ON t.region_id=r.id
WHERE t.active=1;
""",
    "conditions": """
SELECT t.id
FROM users t
WHERE t.active=1
AND (t.country='RU' OR t.country='BY')
AND t.id IN (1,2,3)
AND t.created_dt BETWEEN DATE '2026-01-01' AND DATE '2026-12-31';
""",
    "nested_select": """
SELECT t.id,t.name
FROM users t
WHERE t.id IN (
    SELECT s.user_id
    FROM sales s
    WHERE s.amount>100
);
""",
    "comments": """
-- Отчёт по пользователям
SELECT
    t.id, -- Идентификатор
    t.name,
    /* Количество заказов */
    COUNT(s.id) AS orders_count
FROM users t
/* Подключаем продажи */
LEFT JOIN sales s ON t.id=s.user_id
GROUP BY t.id,t.name;
""",
    "string_literals": """
SELECT t.id,t.name
FROM users t
WHERE t.name='AND;OR'
AND t.status <> 'IN (1,2)'
ORDER BY t.id;
""",
    "aggregates": """
SELECT t.region_id,COUNT(*) AS users_count,SUM(t.amount) AS total
FROM users t
GROUP BY t.region_id
HAVING COUNT(*)>5
ORDER BY t.region_id;
""",
}


class FormatterTests(unittest.TestCase):
    def test_cases(self):
        for name, source in CASES.items():
            with self.subTest(case=name):
                formatted = format_sql(source)

                # Проверка сохранности SQL уже выполняется
                # внутри format_sql().

                # Проверяем идемпотентность:
                # повторное форматирование ничего не меняет.
                self.assertEqual(
                    formatted,
                    format_sql(formatted),
                    f"Неидемпотентен: {name}",
                )


    def test_p1_multiline_literal_preserved(self):
        # Строка из четырёх пробелов внутри литерала — это данные.
        source = "SELECT 'first\n    \nlast' AS text_value FROM t;"
        formatted = format_sql(source)
        self.assertIn("'first\n    \nlast'", formatted)
        self.assertEqual(formatted, format_sql(formatted))

    def test_p1_blank_line_whitespace_removed(self):
        source = "SELECT a FROM t\n    \nWHERE a = 1;"
        formatted = format_sql(source)
        self.assertNotIn("\n    \n", formatted)
        self.assertEqual(formatted, format_sql(formatted))

    def test_p1_group_order_comments(self):
        cases = [
            (
                "SELECT a, b FROM t GROUP BY a,\n-- field b\nb;",
                "GROUP BY\n    a\n    -- field b\n    , b",
            ),
            (
                "SELECT a, b FROM t ORDER BY a,\n-- field b\nb;",
                "ORDER BY\n    a\n    -- field b\n    , b",
            ),
            (
                "SELECT a, b FROM t GROUP BY a, b -- field b\n;",
                "GROUP BY\n    a\n    , b -- field b",
            ),
        ]
        for source, expected in cases:
            with self.subTest(source=source):
                formatted = format_sql(source)
                self.assertIn(expected, formatted)
                self.assertEqual(formatted, format_sql(formatted))

    def test_p1_comments_and_literal_tokens_unchanged(self):
        from formatter import validate_sql_unchanged
        source = "SELECT a FROM t GROUP BY a,\n-- field b\nb;"
        formatted = format_sql(source)
        validate_sql_unchanged(source, formatted)

    def test_groupby_header_comment_nested(self):
        source = ("SELECT t.user_id FROM users t INNER JOIN (\n"
                  "SELECT s.user_id, SUM(s.amount) AS total FROM sales s\n"
                  "GROUP BY -- group fields\n"
                  "    1,\n"
                  "    2\n"
                  ") sub ON t.user_id = sub.user_id;")
        formatted = format_sql(source)
        self.assertIn("-- group fields", formatted)
        self.assertIn("GROUP BY\n    1\n    , 2", formatted)
        self.assertEqual(formatted, format_sql(formatted))

    def test_rejects_changed_sql(self):
        from formatter import validate_sql_unchanged

        with self.assertRaises(ValueError):
            validate_sql_unchanged(
                "SELECT 1",
                "SELECT 2",
            )


    def test_spacing_before_sections_and_join(self):
        source = ("SELECT a FROM t\n\n\n\n"
                  "-- group comment\n\nGROUP BY a, b\n\n\n"
                  "LEFT JOIN x ON t.id=x.id\n\n\nWHERE a=1;")
        # Проверяем непосредственно правило пробелов отдельно от остальных
        # трансформаций JOIN/WHERE.
        from formatter import format_clause_spacing
        result = format_clause_spacing(source)
        self.assertIn("\n\n-- group comment", result)
        self.assertIn("-- group comment\n\nGROUP BY", result)
        self.assertNotIn("\n\n\n", result)
        self.assertEqual(result, format_clause_spacing(result))

    def test_spacing_invisible_blank_lines(self):
        from formatter import format_clause_spacing
        source = "SELECT a FROM t\n\u00a0\n\t\nGROUP BY a, b"
        result = format_clause_spacing(source)
        self.assertEqual(result, "SELECT a FROM t\n\nGROUP BY a, b")


class B2SafetyTests(unittest.TestCase):
    def test_cr_inputs_are_returned_verbatim_on_both_calls(self):
        from unittest.mock import patch
        cases = [
            "SELECT id,\r\n name FROM users;",
            "SELECT 'first\r\n  last' AS txt FROM t;",
            "SELECT 'first\rlast' AS txt FROM t;",
            "SELECT a -- keep\r\nFROM t;\r\n",
            "SELECT /* keep\r\n  comment */ a FROM t;",
            "SELECT a\nFROM t\rWHERE a=1;",
            "SELECT a FROM t;\r",
        ]
        for source in cases:
            with self.subTest(source=source):
                # Refuse before even the preliminary AST-based normalizer.
                with patch('formatter.normalize_groupby_header_comments') as normalize:
                    first_diagnostics, second_diagnostics = [], []
                    first = format_sql(source, diagnostics=first_diagnostics)
                    second = format_sql(first, diagnostics=second_diagnostics)
                    normalize.assert_not_called()
                self.assertEqual(first.encode('utf-8'), source.encode('utf-8'))
                self.assertEqual(second, first)
                self.assertEqual(first_diagnostics, second_diagnostics)
                self.assertEqual([d.code for d in first_diagnostics], ['SQLFMT-E003'])

    def test_cr_warning_goes_to_stderr_without_stdout(self):
        import contextlib
        import io
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            self.assertEqual(format_sql('SELECT 1;\r\n'), 'SELECT 1;\r\n')
        self.assertEqual(output.getvalue(), '')
        self.assertIn('SQLFMT-E003', errors.getvalue())

    def test_nested_select_overlap_is_stable_and_preserves_sql(self):
        from formatter import sql_tokens, validate_sql_unchanged, remove_formatter_where_prefix
        cases = [
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x,y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT\n    x\n    , y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x FROM u WHERE b=2 AND x IN (\nSELECT y,z FROM v\n)\n);",
        ]
        # B3.2: explicitly approved replacement of the B2 fallback output.
        expected = (
            'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n'
            '    AND id IN (\n        SELECT\n            x\n            , y\n'
            '        FROM u\n    )\n;\n'
        )
        deeper_expected = (
            'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n'
            '    AND id IN (\n        SELECT\n            x\n        FROM u\n\n'
            '        WHERE 1=1\n            AND b = 2\n            AND x IN (\n'
            '                SELECT\n                    y\n                    , z\n'
            '                FROM v\n            )\n    )\n;\n'
        )
        for index, source in enumerate(cases):
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                second = format_sql(first, diagnostics=[])
                self.assertEqual(first, second)
                before, before_comments = sql_tokens(source)
                after, after_comments = sql_tokens(first)
                self.assertEqual(remove_formatter_where_prefix(before),
                                 remove_formatter_where_prefix(after))
                self.assertEqual(before_comments, after_comments)
                validate_sql_unchanged(source, first)
                self.assertEqual(first, expected if index < 2 else deeper_expected)
                self.assertFalse(any(d.code == 'SQLFMT-E001' for d in warnings))

    def test_nested_query_with_literals_and_comments_is_preserved(self):
        from formatter import sql_tokens
        source = ("SELECT id FROM t WHERE a=1 AND id IN (\n"
                  "SELECT 'a  b' AS x, -- keep\n y FROM u\n);")
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(first, format_sql(first, diagnostics=[]))
        self.assertEqual(sql_tokens(source), sql_tokens(first))
        self.assertIn("'a  b'", first)
        self.assertIn('-- keep', first)
        # The existing comment guard already skips the outer WHERE here.

    def test_ast_edits_retain_rule_and_atomic_group(self):
        from unittest.mock import patch
        from formatter_modules.formatter_edits import plan_edits
        with patch('formatter.plan_edits', wraps=plan_edits) as planner:
            format_sql("SELECT a, -- keep\n b FROM t;", diagnostics=[])
        edits = planner.call_args.args[1]
        comment_edits = [e for e in edits if e.rule_id == 'COMMENT-LIST']
        self.assertGreaterEqual(len(comment_edits), 3)
        self.assertEqual(len({e.group_id for e in comment_edits}), 1)
        self.assertIsNotNone(comment_edits[0].group_id)
        self.assertIn('select_clause', comment_edits[0].group_id)
        self.assertTrue(all(e.owner for e in comment_edits))

    def test_select_word_in_literal_is_not_a_nested_query(self):
        source = "SELECT 'SELECT x FROM y' AS txt FROM t;"
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(first, format_sql(first, diagnostics=[]))
        self.assertEqual(first, "SELECT\n    'SELECT x FROM y' AS txt\nFROM t\n;\n")
        self.assertFalse(any('дочерний SELECT' in d.message for d in warnings))


class B31SimpleQueryTests(unittest.TestCase):
    CASES = [
        ('SELECT id, name FROM users WHERE active=1;',
         'SELECT\n    id\n    , name\nFROM users\n\nWHERE active = 1\n;\n'),
        ('SELECT id FROM users;', 'SELECT\n    id\nFROM users\n;\n'),
        ('SELECT u.id AS user_id,u.name display_name,u.age FROM users u;',
         'SELECT\n    u.id AS user_id\n    , u.name display_name\n    , u.age\nFROM users u\n;\n'),
        ('SELECT DISTINCT id,name FROM users;',
         'SELECT DISTINCT\n    id\n    , name\nFROM users\n;\n'),
        ('SELECT *,u.id FROM users u WHERE u.id>=10;',
         'SELECT\n    *\n    , u.id\nFROM users u\n\nWHERE u.id >= 10\n;\n'),
        ("SELECT 'a  b' AS txt,id FROM users WHERE name='it''s  fine';",
         "SELECT\n    'a  b' AS txt\n    , id\nFROM users\n\nWHERE name = 'it''s  fine'\n;\n"),
        ('SELECT id FROM users WHERE active=1 AND age>18;',
         'SELECT\n    id\nFROM users\n\nWHERE 1=1\n    AND active = 1\n    AND age > 18\n;\n'),
        ('SELECT id FROM users WHERE age BETWEEN 1 AND 5;',
         'SELECT\n    id\nFROM users\n\nWHERE age BETWEEN 1 AND 5\n;\n'),
    ]

    def test_exact_simple_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_simple_idempotence_independently(self):
        # Do not hide second-pass failures behind exact-output assertions.
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_simple_token_preservation_independently(self):
        from formatter import validate_sql_unchanged, sql_tokens
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(sql_tokens(source)[1], sql_tokens(first)[1])
                self.assertFalse(any(d.code in ('SQLFMT-E001', 'SQLFMT-E002')
                                     for d in self._diagnostics(source)))

    @staticmethod
    def _diagnostics(source):
        diagnostics = []
        format_sql(source, diagnostics=diagnostics)
        return diagnostics

    def test_whitespace_variants_have_one_result(self):
        expected = self.CASES[0][1]
        for source in (
            'SELECT id,name FROM users WHERE active=1;',
            '  SELECT  id ,  name\n\n  FROM   users\n WHERE active = 1 ;',
            '\tSELECT\n id\n, name\n\nFROM\n users\n\n\nWHERE active=1\n;',
        ):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, expected)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_comparison_operators_remain_whole(self):
        from formatter import sql_tokens
        for operator in ('=', '<', '>', '<=', '>=', '<>', '!='):
            source = f'SELECT id FROM users WHERE age{operator}18;'
            with self.subTest(operator=operator):
                first = format_sql(source, diagnostics=[])
                self.assertIn(f'WHERE age {operator} 18\n;', first)
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_comment_attachment_and_literal_bytes(self):
        from formatter import sql_tokens
        cases = [
            ("SELECT id, -- identifier\n name FROM users WHERE name='a  b';",
             'id -- identifier\n    , name\nFROM users'),
            ('SELECT\n-- identifier\nid FROM users;',
             'SELECT\n    -- identifier\n    id\nFROM users'),
            ('SELECT id -- final field\nFROM users\n-- active only\nWHERE active=1;',
             'id -- final field\nFROM users\n-- active only\nWHERE active = 1'),
            ('SELECT id FROM users WHERE active/* keep */=1;',
             'active/* keep */= 1'),
        ]
        for source, fragment in cases:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertIn(fragment, first)
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_new_pass_skips_out_of_scope_constructs(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import simple_query_gap_edits
        cases = [
            'WITH c AS (SELECT id FROM t) SELECT id FROM c;',
            'SELECT id FROM t WHERE id IN (SELECT id FROM u);',
            'SELECT t.id FROM t JOIN u ON t.id=u.id;',
            'SELECT id FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY id)=1;',
            'SELECT ROW_NUMBER() OVER (ORDER BY id) FROM t;',
            'SELECT id FROM t GROUP BY id;',
            'SELECT id FROM t UNION ALL SELECT id FROM u;',
            'SELECT a.id FROM a,b;',
        ]
        for source in cases:
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                self.assertEqual(simple_query_gap_edits(source, tree), [])

    def test_boundary_pass_edits_only_whitespace(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import simple_query_gap_edits
        source = '  SELECT id, name FROM users WHERE active>=1;'
        tree = Linter(dialect='teradata').parse_string(source).tree
        edits = simple_query_gap_edits(source, tree)
        self.assertTrue(edits)
        for edit in edits:
            self.assertFalse(source[edit.start:edit.end].strip())
            self.assertFalse(edit.replacement.strip())
            self.assertIsNotNone(edit.group_id)


class B32NestedQueryTests(unittest.TestCase):
    CASES = [
        ('SELECT id FROM t WHERE id IN (SELECT x,y FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE id IN (\n    SELECT\n        x\n        , y\n    FROM u\n)\n;\n'),
        ('SELECT q.id FROM (SELECT id,name FROM u WHERE active=1) q;',
         'SELECT\n    q.id\nFROM (\n    SELECT\n        id\n        , name\n    FROM u\n\n    WHERE active = 1\n) q\n;\n'),
        ('SELECT id FROM t WHERE a=1 AND id IN (SELECT x,y FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a = 1\n    AND id IN (\n'
         '        SELECT\n            x\n            , y\n        FROM u\n    )\n;\n'),
        ("SELECT id FROM t WHERE note='SELECT FROM WHERE' AND id IN (SELECT 'SELECT FROM WHERE' AS x FROM u);",
         "SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND note = 'SELECT FROM WHERE'\n"
         "    AND id IN (\n        SELECT\n            'SELECT FROM WHERE' AS x\n        FROM u\n    )\n;\n"),
        ('SELECT id FROM t WHERE id IN ( -- open\nSELECT x FROM u -- close\n);',
         'SELECT\n    id\nFROM t\n\nWHERE id IN ( -- open\n    SELECT\n        x\n    FROM u -- close\n)\n;\n'),
        ('SELECT q.x FROM (\n-- inner\nSELECT x,y FROM u\n) q;',
         'SELECT\n    q.x\nFROM (\n    -- inner\n    SELECT\n        x\n        , y\n    FROM u\n) q\n;\n'),
        ('SELECT (SELECT x FROM u WHERE x=1) AS value,id FROM t;',
         'SELECT\n    (\n        SELECT\n            x\n        FROM u\n\n        WHERE x = 1\n    ) AS value\n    , id\nFROM t\n;\n'),
        ('SELECT q.x FROM (SELECT p.x FROM (SELECT x,y FROM v) p) q;',
         'SELECT\n    q.x\nFROM (\n    SELECT\n        p.x\n    FROM (\n        SELECT\n            x\n            , y\n        FROM v\n    ) p\n) q\n;\n'),
        ('SELECT id FROM t WHERE a BETWEEN 1 AND 3 AND id IN (SELECT x FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND a BETWEEN 1 AND 3\n    AND id IN (\n        SELECT\n            x\n        FROM u\n    )\n;\n'),
        ('SELECT id FROM t WHERE a=1 OR id IN (SELECT x FROM u);',
         'SELECT\n    id\nFROM t\n\nWHERE a = 1 OR id IN (\n    SELECT\n        x\n    FROM u\n)\n;\n'),
    ]

    def test_exact_nested_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_nested_idempotence_independently(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_nested_tokens_literals_comments_independently(self):
        from formatter import sql_tokens, validate_sql_unchanged, remove_formatter_where_prefix
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                before, comments = sql_tokens(source)
                after, actual_comments = sql_tokens(first)
                self.assertEqual(comments, actual_comments)
                self.assertEqual(remove_formatter_where_prefix(before), remove_formatter_where_prefix(after))
                self.assertEqual([t for t in before if 'literal' in t[0] and t[0] != 'numeric_literal'],
                                 [t for t in after if 'literal' in t[0] and t[0] != 'numeric_literal'])

    def test_indentation_ignores_original_columns(self):
        expected = self.CASES[2][1]
        for source in (
                '   SELECT id FROM t WHERE a=1 AND id IN (\n SELECT x,y FROM u\n);',
                '\tSELECT id\n  FROM t\n WHERE a = 1 AND id IN (\n\t\tSELECT x, y\n FROM u\n        );',
                expected):
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_where_prefix_is_exact_and_validator_stays_strict(self):
        from formatter import validate_sql_unchanged, sql_tokens
        source, expected = self.CASES[2]
        self.assertEqual(len(sql_tokens(expected)[0]) - len(sql_tokens(source)[0]), 4)
        validate_sql_unchanged(source, expected)
        for altered in (expected.replace('WHERE 1=1', 'WHERE 2=2'),
                        expected.replace('AND a = 1', 'AND a = 2'),
                        expected.replace('AND id IN', 'OR id IN'),
                        expected.replace('FROM u', 'FROM v')):
            with self.subTest(altered=altered), self.assertRaises(ValueError):
                validate_sql_unchanged(source, altered)
        for source, expected in (self.CASES[3], self.CASES[4]):
            altered = expected.replace("'SELECT FROM WHERE'", "'changed'").replace('-- open', '-- changed')
            with self.subTest(source=source), self.assertRaises(ValueError):
                validate_sql_unchanged(source, altered)

    def test_existing_prefix_siblings_and_multiline_literals_are_stable(self):
        from formatter import validate_sql_unchanged
        cases = [
            'SELECT id FROM t WHERE 1 = 1 AND a=1 AND id IN (SELECT x FROM u);',
            'SELECT id FROM t WHERE id IN (SELECT x FROM u) AND id IN (SELECT y FROM v);',
            "SELECT id FROM t WHERE a=1 AND id IN (SELECT 'a\n\nb' AS x FROM u);",
            'SELECT q.x FROM (/* inner */ SELECT x FROM u /* tail */) q;',
            '\nSELECT id FROM t WHERE id IN (SELECT x FROM u);\nSELECT q.x FROM (SELECT x FROM u WHERE x>=2) q;',
        ]
        for source in cases:
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                self.assertEqual(first, format_sql(first, diagnostics=[]))
                validate_sql_unchanged(source, first)
                self.assertEqual(warnings, [])
        self.assertEqual(format_sql(cases[0], diagnostics=[]).count('WHERE 1=1'), 1)
        self.assertIn("'a\n\nb'", format_sql(cases[2], diagnostics=[]))

    def test_no_parent_edit_covers_child_and_no_e001_is_suppressed(self):
        from unittest.mock import patch
        from sqlfluff.core import Linter
        from formatter import walk
        from formatter_modules.formatter_edits import plan_edits
        source = self.CASES[2][0]
        warnings = []
        with patch('formatter.plan_edits', wraps=plan_edits) as planner:
            format_sql(source, diagnostics=warnings)
        self.assertFalse(any(d.code == 'SQLFMT-E001' for d in warnings))
        for call in planner.call_args_list:
            snapshot, candidates = call.args[:2]
            tree = Linter(dialect='teradata').parse_string(snapshot).tree
            children = [n.pos_marker.source_slice for n in walk(tree) if n.is_type('select_statement')][1:]
            for edit in candidates:
                self.assertFalse(edit.rule_id == 'LEGACY-AST' and edit.owner.startswith('where_clause'))
                for child in children:
                    self.assertFalse(edit.start < child.start and edit.end > child.start)
                    self.assertFalse(edit.start < child.stop and edit.end > child.stop)

    def test_nested_prepass_group_rejects_protection_or_conflict_atomically(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import Edit, plan_edits
        source = self.CASES[2][0]
        edits, _ = nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree)
        self.assertGreater(len(edits), 2)
        self.assertEqual(len({e.group_id for e in edits}), 1)
        target = next(e for e in edits if e.start < e.end)
        accepted, warnings = plan_edits(source, edits, protected=[(target.start, target.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(w.code == 'SQLFMT-E002' for w in warnings))
        conflict = Edit(target.start, target.start, ' ', 'TEST-CONFLICT')
        accepted, warnings = plan_edits(source, [conflict] + edits, protected=[])
        self.assertEqual(accepted, [conflict])
        self.assertTrue(any(w.code == 'SQLFMT-E001' for w in warnings))

    def test_out_of_scope_queries_are_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in (
                'WITH c AS (SELECT id FROM u) SELECT id FROM c;',
                'SELECT t.id FROM t JOIN (SELECT id FROM u) q ON q.id=t.id;',
                'SELECT id FROM t WHERE id IN (SELECT id FROM u) QUALIFY id=1;',
                'SELECT ROW_NUMBER() OVER (ORDER BY id) FROM (SELECT id FROM u) q;',
                'SELECT id FROM t UNION SELECT id FROM (SELECT id FROM u) q;',
                'SELECT id FROM t WHERE id IN (SELECT id FROM u GROUP BY id);'):
            with self.subTest(source=source):
                self.assertEqual(nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree), ([], set()))



class B33BasicClauseTests(unittest.TestCase):
    CASES = [
        ('select id from users where active = 1;',
         'SELECT\n    id\nFROM users\n\nWHERE active = 1\n;\n'),
        ('SeLeCt Id from Users WhErE active=1;',
         'SELECT\n    Id\nFROM Users\n\nWHERE active = 1\n;\n'),
        ("select 'select FROM where' AS \"where\",MixedName from MixedTable where MixedName='WHERE';",
         "SELECT\n    'select FROM where' AS \"where\"\n    , MixedName\nFROM MixedTable\n\nWHERE MixedName = 'WHERE'\n;\n"),
        ('SELECT a.id,b.name FROM a,b;',
         'SELECT\n    a.id\n    , b.name\nFROM a\n    , b\n;\n'),
        ('SELECT id,\n-- first\n-- second\nname FROM users;',
         'SELECT\n    id\n    -- first\n    -- second\n    , name\nFROM users\n;\n'),
        ("SELECT id FROM t WHERE active=1 AND (country='RU' OR country='BY');",
         "SELECT\n    id\nFROM t\n\nWHERE 1=1\n    AND active = 1\n    AND (country = 'RU' OR country = 'BY')\n;\n"),
        ('SELECT x+y AS total,-x AS neg,COUNT(*) AS n FROM t;',
         'SELECT\n    x + y AS total\n    , -x AS neg\n    , COUNT(*) AS n\nFROM t\n;\n'),
        ('select distinct Id from Users where a=1 and b=2;',
         'SELECT distinct\n    Id\nFROM Users\n\nWHERE 1=1\n    AND a = 1\n    and b = 2\n;\n'),
    ]

    def test_exact_basic_outputs(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_basic_idempotence_independently(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, format_sql(first, diagnostics=[]))

    def test_basic_validation_independently(self):
        from formatter import validate_sql_unchanged
        for source, _ in self.CASES:
            with self.subTest(source=source):
                validate_sql_unchanged(source, format_sql(source, diagnostics=[]))

    def test_all_nine_former_basic_failures_match_existing_goldens(self):
        from tests.contract.test_contract_golden import GOLDEN
        from tests.contract.test_contract_golden_v1_2 import GOLDEN as V12
        from tests.contract.test_contract_edge_v1_2 import GOLDEN as EDGE
        for collection in (GOLDEN, V12):
            for name in ('from_multiple_tables', 'comment_above_element', 'where_or_inside_parentheses'):
                source, expected = collection[name]
                with self.subTest(name=name, collection=id(collection)):
                    actual = format_sql(source, diagnostics=[])
                    self.assertEqual(actual, expected)
                    self.assertEqual(format_sql(actual, diagnostics=[]), actual)
        source, expected = EDGE['consecutive_comment_lines']
        self.assertEqual(format_sql(source, diagnostics=[]), expected)
        self.assertIn('x + y', format_sql('SELECT x+y AS total FROM t;', diagnostics=[]))
        warnings = []
        source = 'SELECT id FROM t WHERE a=1 AND b=2 OR c=3;'
        actual = format_sql(source, diagnostics=warnings)
        self.assertTrue(any(d.code == 'SQLFMT-W001' for d in warnings))
        self.assertNotIn('WHERE 1=1', actual)
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)

    def test_nested_mixed_case_headers_and_prefix_are_stable(self):
        from formatter import validate_sql_unchanged
        source = 'select id from t where a=1 AND id IN (sElEcT x from u where b=2 AND c=3);'
        warnings = []
        first = format_sql(source, diagnostics=warnings)
        self.assertEqual(warnings, [])
        self.assertEqual(first.count('WHERE 1=1'), 2)
        self.assertIn('        SELECT\n            x\n        FROM u', first)
        validate_sql_unchanged(source, first)
        self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_compact_header_boundaries_are_atomic_and_stable(self):
        from formatter import validate_sql_unchanged
        for source in ('select id from t where id IN (select x from u);',
                       'select q.x from(select x from u) q;'):
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                self.assertEqual(warnings, [])
                self.assertIn('\nFROM ', first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)
                validate_sql_unchanged(source, first)

    def test_operator_spacing_preserves_comments_literals_and_unary_signs(self):
        from formatter import sql_tokens, validate_sql_unchanged
        for source in (
                "SELECT x/* keep */+y, -x, x*-2, 'a+b' AS txt FROM t;",
                'SELECT x -- attached to x\n+y FROM t;',
                'SELECT x+y*z/2, x||y FROM t WHERE a+1>=2;',
                'SELECT id FROM t WHERE a -- attached to a\n=1;',
                'SELECT id FROM t WHERE a=/* keep */1;'):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                validate_sql_unchanged(source, first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_prefix_stays_single_and_between_is_not_an_and_chain(self):
        for source, count in (
                ('SELECT id FROM t WHERE a BETWEEN 1 AND 2;', 0),
                ('SELECT id FROM t WHERE a=1;', 0),
                ('SELECT id FROM t WHERE a BETWEEN 1 AND 2 AND b=3;', 1),
                ('SELECT id FROM t WHERE 1=1 AND a=1 AND b=2;', 1),
                ('SELECT id FROM t WHERE 1=1 and a=1;', 1),
                ('SELECT id FROM t WHERE id IN (SELECT x FROM u WHERE a=1 AND b=2);', 1)):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first.count('WHERE 1=1'), count)
                self.assertEqual(format_sql(first, diagnostics=[]), first)


class B33StrictValidatorTests(unittest.TestCase):
    def assertAccepted(self, source, candidate):
        from formatter import validate_sql_unchanged
        validate_sql_unchanged(source, candidate)

    def assertRejected(self, source, candidate):
        from formatter import validate_sql_unchanged
        with self.assertRaises(ValueError):
            validate_sql_unchanged(source, candidate)

    def test_only_ast_clause_headers_can_be_uppercased(self):
        source = "select distinct Id as Alias from MixedTable where Id in ('select FROM WHERE');"
        self.assertAccepted(source, source)
        self.assertAccepted(source, source.replace('select distinct', 'SELECT distinct')
                            .replace('from MixedTable', 'FROM MixedTable').replace('where Id', 'WHERE Id'))
        for old, new in (('distinct', 'DISTINCT'), (' as ', ' AS '), (' in ', ' IN '),
                         ('Id', 'ID'), ('Alias', 'ALIAS'), ('MixedTable', 'MIXEDTABLE'),
                         ("'select FROM WHERE'", "'SELECT FROM WHERE'")):
            with self.subTest(old=old):
                self.assertRejected(source, source.replace(old, new))
        self.assertRejected('SELECT id FROM t;', 'select id FROM t;')
        self.assertRejected('sEleCt id FROM t;', 'Select id FROM t;')
        self.assertRejected('SEL id FROM t;', 'SELECT id FROM t;')
        self.assertRejected('SELECT "where" FROM t;', 'SELECT "WHERE" FROM t;')
        self.assertRejected('SELECT id FROM t -- where\n;', 'SELECT id FROM t -- WHERE\n;')

    def test_tokens_order_types_and_clause_ownership_remain_strict(self):
        source = 'SELECT id FROM t WHERE a=1 AND b=2;'
        for candidate in (
                'SELECT id FROM t HAVING a=1 AND b=2;',
                'SELECT id FROM t WHERE b=2 AND a=1;',
                'SELECT id FROM t WHERE a=1 OR b=2;',
                'SELECT id FROM t WHERE a=1;',
                "SELECT id FROM t WHERE a='1' AND b=2;",
                'SELECT id FROM t WHERE 2=2 AND a=1 AND b=2;',
                'SELECT id FROM t WHERE 1=1 AND a=1 AND b=3;'):
            with self.subTest(candidate=candidate):
                self.assertRejected(source, candidate)

    def test_exact_prefix_allowed_for_eligible_where_only(self):
        for expression in ('a=1 AND b=2', "a=1 AND (b='x' OR b='y')",
                           'a BETWEEN 1 AND 2 AND b=3'):
            with self.subTest(expression=expression):
                self.assertAccepted('SELECT id FROM t WHERE ' + expression + ';',
                                    'SELECT id FROM t WHERE 1=1 AND ' + expression + ';')

    def test_prefix_rejected_for_single_between_or_and_wrong_locations(self):
        for expression in ('a=1', 'a BETWEEN 1 AND 2', 'a=1 OR b=2',
                           'a=1 AND b=2 OR c=3', '(a=1 AND b=2)',
                           'id IN (SELECT x FROM u WHERE a=1 AND b=2)'):
            with self.subTest(expression=expression):
                self.assertRejected('SELECT id FROM t WHERE ' + expression + ';',
                                    'SELECT id FROM t WHERE 1=1 AND ' + expression + ';')
        self.assertRejected('SELECT a=1 AND b=2 FROM t;', 'SELECT 1=1 AND a=1 AND b=2 FROM t;')
        self.assertRejected('SELECT id FROM t WHERE a=1 AND b=2;',
                            'SELECT id FROM t WHERE a=1 AND 1=1 AND b=2;')
        self.assertRejected('SELECT id FROM t WHERE a=1 AND b=2;',
                            'SELECT id FROM t WHERE 1=1 and a=1 AND b=2;')

    def test_existing_prefix_cannot_be_removed_or_duplicated(self):
        for conjunction in ('AND', 'and'):
            source = f'SELECT id FROM t WHERE 1=1 {conjunction} a=1 AND b=2;'
            self.assertAccepted(source, source)
            self.assertRejected(source, 'SELECT id FROM t WHERE a=1 AND b=2;')
            self.assertRejected(source, source.replace('WHERE ', 'WHERE 1=1 AND '))

    def test_nested_where_eligibility_does_not_leak_to_parent_or_sibling(self):
        source = ('SELECT id FROM t WHERE id IN (SELECT x FROM u WHERE a=1 AND b=2) '
                  'OR id IN (SELECT y FROM v WHERE c=3);')
        allowed = source.replace('WHERE a=1', 'WHERE 1=1 AND a=1')
        self.assertAccepted(source, allowed)
        self.assertRejected(source, allowed.replace('WHERE id', 'WHERE 1=1 AND id'))
        self.assertRejected(source, allowed.replace('WHERE c=3', 'WHERE 1=1 AND c=3'))
        both = 'SELECT id FROM t WHERE z=0 AND id IN (SELECT x FROM u WHERE a=1 AND b=2);'
        self.assertAccepted(both, both.replace('WHERE ', 'WHERE 1=1 AND '))



class B41ClauseContextTests(unittest.TestCase):
    GROUP_ORDER = 'SELECT\n    a\n    , b\nFROM t\n\nGROUP BY\n    a\n    , b\n\nORDER BY\n    a DESC\n    , b\n;\n'
    CASES = [
        ('SELECT a,b FROM t GROUP BY a,b ORDER BY a DESC,b;', GROUP_ORDER),
        ('SELECT a FROM t GROUP BY a;', 'SELECT\n    a\nFROM t\n\nGROUP BY a\n;\n'),
        ('SELECT a FROM t ORDER BY a;', 'SELECT\n    a\nFROM t\n\nORDER BY a\n;\n'),
        ('SELECT a,b FROM t,u GROUP BY a,b ORDER BY a DESC,b;',
         GROUP_ORDER.replace('FROM t\n', 'FROM t\n    , u\n')),
        ("SELECT a,b FROM t,u WHERE a=1 AND b='x' GROUP BY a,b ORDER BY a DESC,b;",
         GROUP_ORDER.replace('FROM t\n', "FROM t\n    , u\n\nWHERE 1=1\n    AND a = 1\n    AND b = 'x'\n")),
        ('SELECT a FROM t HAVING a>1 AND a<3 ORDER BY a;',
         'SELECT\n    a\nFROM t\n\nHAVING a>1 AND a<3\n\nORDER BY a\n;\n'),
        ('select a from t group by a,b order by a desc,b;',
         'SELECT\n    a\nFROM t\n\ngroup by\n    a\n    , b\n\norder by\n    a desc\n    , b\n;\n'),
        ("SELECT COALESCE(a,b) AS x FROM t GROUP BY COALESCE(a,b),'a,b' ORDER BY x DESC NULLS LAST,a;",
         "SELECT\n    COALESCE(a,b) AS x\nFROM t\n\nGROUP BY\n    COALESCE(a,b)\n    , 'a,b'\n\nORDER BY\n    x DESC NULLS LAST\n    , a\n;\n"),
    ]

    def test_exact_first_output(self):
        for source, expected in self.CASES:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source, diagnostics=[]), expected)

    def test_idempotence_independent_of_expected(self):
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_token_and_comment_preservation_independently(self):
        from formatter import validate_sql_unchanged, sql_tokens
        for source, _ in self.CASES:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(sql_tokens(source)[1], sql_tokens(first)[1])

    def test_whitespace_variants_have_identical_first_result(self):
        variants = [
            'SELECT a,b FROM t GROUP BY a,b ORDER BY a DESC,b;',
            'SELECT\n a,\n b\nFROM t\nGROUP BY a,b\nORDER BY a DESC,b;',
            '\t SELECT  a , b\n   FROM\t t\n\n\t GROUP\tBY\n a ,\n\tb\n  ORDER  BY a DESC , b;',
            self.GROUP_ORDER,
        ]
        for source in variants:
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                self.assertEqual(first, self.GROUP_ORDER)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_both_original_group_order_goldens(self):
        from tests.contract.test_contract_golden import GOLDEN
        from tests.contract.test_contract_golden_v1_2 import GOLDEN as V12
        for cases in (GOLDEN, V12):
            source, expected = cases['group_and_order_multiple']
            self.assertEqual(format_sql(source, diagnostics=[]), expected)
            self.assertEqual(format_sql(expected, diagnostics=[]), expected)

    def test_multiple_from_with_each_list_clause(self):
        for clause in ('GROUP BY a,b', 'ORDER BY a,b', 'GROUP BY a,b ORDER BY a,b'):
            source = 'SELECT a,b FROM users a,payments b ' + clause + ';'
            with self.subTest(clause=clause):
                first = format_sql(source, diagnostics=[])
                self.assertIn('FROM users a\n    , payments b\n\n', first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_having_predicate_bytes_are_opaque(self):
        from sqlfluff.core import Linter
        from formatter import walk
        source = "SELECT a FROM t WHERE a=1 AND b=2 GROUP BY a HAVING SUM(a+1)>2 AND MAX(b)='  x' ORDER BY a;"
        first = format_sql(source, diagnostics=[])
        def having(sql):
            return next(s.raw for s in walk(Linter(dialect='teradata').parse_string(sql).tree)
                        if s.is_type('having_clause'))
        self.assertEqual(having(source), having(first))
        self.assertIn('WHERE 1=1', first)
        self.assertNotIn('HAVING 1=1', first)
        self.assertEqual(format_sql(first, diagnostics=[]), first)

    def test_window_order_and_other_future_contexts_not_claimed(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        for source in (
                'SELECT ROW_NUMBER() OVER (ORDER BY a,b) AS n FROM t ORDER BY n;',
                'SELECT a FROM t QUALIFY ROW_NUMBER() OVER (ORDER BY a)=1;',
                'SELECT a FROM t JOIN u ON t.a=u.a GROUP BY a;',
                'WITH c AS (SELECT a FROM t) SELECT a FROM c ORDER BY a;',
                'SELECT a FROM t UNION ALL SELECT a FROM u;',
                'SELECT a FROM t GROUP BY a,\n-- b\nb;'):
            with self.subTest(source=source):
                tree = Linter(dialect='teradata').parse_string(source).tree
                self.assertEqual(nested_query_gap_edits(source, tree, include_simple=True), ([], set()))

    def test_comments_literals_and_existing_where_with_order(self):
        from formatter import validate_sql_unchanged
        for source in (
                "SELECT a, -- keep\n b FROM t WHERE a='a  b' AND b=2 GROUP BY a,b ORDER BY a,b;",
                "SELECT a FROM t WHERE a=1 AND b='x' ORDER BY a;",
                'SELECT a FROM t WHERE 1=1 AND a=1 AND b=2 GROUP BY a ORDER BY a;',
                'SELECT a FROM t WHERE a BETWEEN 1 AND 2 GROUP BY a ORDER BY a;'):
            with self.subTest(source=source):
                first = format_sql(source, diagnostics=[])
                validate_sql_unchanged(source, first)
                self.assertEqual(format_sql(first, diagnostics=[]), first)
                if '-- keep' in source:
                    self.assertIn('a -- keep\n    , b', first)

    def test_new_list_edits_remain_one_atomic_group(self):
        from sqlfluff.core import Linter
        from formatter_modules.formatter_clause_gaps import nested_query_gap_edits
        from formatter_modules.formatter_edits import plan_edits
        source = self.CASES[0][0]
        edits, owners = nested_query_gap_edits(source, Linter(dialect='teradata').parse_string(source).tree,
                                              include_simple=True)
        self.assertEqual(owners, {0})
        self.assertEqual(len({e.group_id for e in edits}), 1)
        edit = next(e for e in edits if e.start < e.end)
        accepted, warnings = plan_edits(source, edits, protected=[(edit.start, edit.end)])
        self.assertEqual(accepted, [])
        self.assertTrue(any(d.code == 'SQLFMT-E002' for d in warnings))


if __name__ == "__main__":
    unittest.main()
