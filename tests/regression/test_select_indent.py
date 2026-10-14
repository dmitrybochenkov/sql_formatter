import unittest
from formatter import format_sql


class SelectIndentTests(unittest.TestCase):
    def test_multiline_select_with_leading_commas(self):
        source = ("SELECT\n"
                  "t.user_id\n"
                  "\n"
                  ", t.user_name -- ведущая запятая\n"
                  ", sub.total_amount\n"
                  "FROM prd_tables.users_v t;")
        result = format_sql(source)
        self.assertIn("SELECT\n    t.user_id", result)
        self.assertIn("\n    , t.user_name -- ведущая запятая", result)
        self.assertIn("\n    , sub.total_amount", result)
        self.assertEqual(result, format_sql(result))

    def test_nested_select_indent(self):
        source = ("SELECT\n"
                  "a.id\n"
                  ", sub.total_amount\n"
                  "FROM t a\n"
                  "INNER JOIN (\n"
                  "    SELECT\n"
                  "    user_id\n"
                  "    , SUM(amount) AS total_amount\n"
                  "    FROM payments\n"
                  "    GROUP BY user_id\n"
                  ") sub ON a.id=sub.user_id;")
        result = format_sql(source)
        self.assertIn("SELECT\n    a.id", result)
        self.assertIn("    SELECT\n        user_id", result)
        self.assertIn("\n        , SUM(amount) AS total_amount", result)
        self.assertEqual(result, format_sql(result))


if __name__ == "__main__":
    unittest.main()
