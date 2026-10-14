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
        from formatter import sql_tokens, validate_sql_unchanged
        cases = [
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x,y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT\n    x\n    , y FROM u\n);",
            "SELECT id FROM t WHERE a=1 AND id IN (\nSELECT x FROM u WHERE b=2 AND x IN (\nSELECT y,z FROM v\n)\n);",
        ]
        for source in cases:
            with self.subTest(source=source):
                warnings = []
                first = format_sql(source, diagnostics=warnings)
                second = format_sql(first, diagnostics=[])
                self.assertEqual(first, second)
                self.assertEqual(sql_tokens(source), sql_tokens(first))
                validate_sql_unchanged(source, first)
                self.assertIn('SELECT\n    id', first)
                self.assertIn('SELECT\n    ', first[first.index('IN ('):])
                self.assertNotIn('WHERE 1=1', first)
                self.assertTrue(any(d.code == 'SQLFMT-E001' and 'дочерний SELECT' in d.message
                                    for d in warnings))

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
        self.assertEqual(first, "SELECT\n    'SELECT x FROM y' AS txt FROM t\n;\n")
        self.assertFalse(any('дочерний SELECT' in d.message for d in warnings))

if __name__ == "__main__":
    unittest.main()
