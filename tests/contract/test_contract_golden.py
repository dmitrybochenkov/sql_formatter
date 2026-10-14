"""Golden tests for Teradata SQL Formatter contract v1.1.

Run from the directory containing formatter.py:
    python -m unittest -v test_contract_golden.py

These tests intentionally compare the ENTIRE output, not fragments.
Current implementation may fail: this is a contract-first test suite.
"""
import textwrap
import unittest

from formatter import format_sql


def sql(s):
    return textwrap.dedent(s).strip("\n") + "\n"


GOLDEN = {
    "select_random_whitespace": (
        "SELECT       a,\n  b,\n\n        c\n    ,\n d\n\nFROM       users;",
        sql("""\
        SELECT
            a
            , b
            , c
            , d
        FROM users
        ;"""),
    ),
    "select_distinct": (
        "SELECT DISTINCT     t.user_id, t.name FROM users t;",
        sql("""\
        SELECT DISTINCT
            t.user_id
            , t.name
        FROM users t
        ;"""),
    ),
    "select_star": (
        "SELECT *,t.id FROM users t;",
        sql("""\
        SELECT
            *
            , t.id
        FROM users t
        ;"""),
    ),
    "from_multiple_tables": (
        "SELECT a.id,b.name FROM a, b;",
        sql("""\
        SELECT
            a.id
            , b.name
        FROM a
            , b
        ;"""),
    ),
    "join_on_alignment": (
        "SELECT t.id,s.amount FROM users t INNER JOIN sales s ON s.user_id=t.id AND s.status='OK';",
        sql("""\
        SELECT
            t.id
            , s.amount
        FROM users t

        INNER JOIN sales s
        ON s.user_id = t.id
            AND s.status = 'OK'
        ;"""),
    ),
    "where_two_ands": (
        "SELECT id FROM t WHERE active=1 AND amount>0;",
        sql("""\
        SELECT
            id
        FROM t

        WHERE 1=1
            AND active = 1
            AND amount > 0
        ;"""),
    ),
    "where_or_inside_parentheses": (
        "SELECT id FROM t WHERE active=1 AND (country='RU' OR country='BY');",
        sql("""\
        SELECT
            id
        FROM t

        WHERE 1=1
            AND active = 1
            AND (country = 'RU' OR country = 'BY')
        ;"""),
    ),
    "group_and_order_multiple": (
        "SELECT a,b FROM t GROUP BY a,b ORDER BY a DESC,b;",
        sql("""\
        SELECT
            a
            , b
        FROM t

        GROUP BY
            a
            , b

        ORDER BY
            a DESC
            , b
        ;"""),
    ),
    "having_two_ands": (
        "SELECT a,COUNT(*) AS n FROM t GROUP BY a HAVING COUNT(*)>1 AND SUM(amount)>100;",
        sql("""\
        SELECT
            a
            , COUNT(*) AS n
        FROM t

        GROUP BY a

        HAVING 1=1
            AND COUNT(*) > 1
            AND SUM(amount) > 100
        ;"""),
    ),
    "comment_after_field": (
        "SELECT t.id, -- identifier\n t.name FROM users t;",
        sql("""\
        SELECT
            t.id -- identifier
            , t.name
        FROM users t
        ;"""),
    ),
    "comment_above_element": (
        "SELECT t.id,\n-- name of user\nt.name FROM users t;",
        sql("""\
        SELECT
            t.id
            -- name of user
            , t.name
        FROM users t
        ;"""),
    ),
    "ctes_separated": (
        "WITH sales AS (SELECT user_id FROM payments), users AS (SELECT user_id FROM customers) SELECT user_id FROM users;",
        sql("""\
        WITH sales AS (
            SELECT
                user_id
            FROM payments
        )

        , users AS (
            SELECT
                user_id
            FROM customers
        )

        SELECT
            user_id
        FROM users
        ;"""),
    ),
    "window_multiple_keys": (
        "SELECT ROW_NUMBER() OVER (PARTITION BY user_id,event_type ORDER BY created_at DESC,event_id DESC) AS rn FROM events;",
        sql("""\
        SELECT
            ROW_NUMBER() OVER (
                PARTITION BY
                    user_id
                    , event_type
                ORDER BY
                    created_at DESC
                    , event_id DESC
            ) AS rn
        FROM events
        ;"""),
    ),
    "qualify": (
        "SELECT user_id FROM events QUALIFY ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)=1 AND amount>0;",
        sql("""\
        SELECT
            user_id
        FROM events

        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY user_id
            ORDER BY created_at DESC
        ) = 1
            AND amount > 0
        ;"""),
    ),
    "union_all": (
        "SELECT id FROM a UNION ALL SELECT id FROM b;",
        sql("""\
        SELECT
            id
        FROM a

        UNION ALL

        SELECT
            id
        FROM b
        ;"""),
    ),
    "uppercase_keywords": (
        "select id from users where active = 1;",
        sql("""\
        SELECT
            id
        FROM users

        WHERE active = 1
        ;"""),
    ),
}


class ContractGoldenTests(unittest.TestCase):
    def test_exact_output_and_idempotence(self):
        for name, (source, expected) in GOLDEN.items():
            with self.subTest(case=name):
                actual = format_sql(source)
                self.assertEqual(actual, expected)
                self.assertEqual(format_sql(actual), actual)


if __name__ == "__main__":
    unittest.main()
