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

if __name__ == "__main__":
    unittest.main()
