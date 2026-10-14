"""Additional contract-first golden tests for Teradata formatter v1.2.

Place next to formatter.py and run:
    python -m unittest -v test_contract_golden_v1_2 test_contract_edge_v1_2

Expected failures are implementation gaps, not permission to weaken the contract.
"""
import contextlib
import io
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from formatter import format_sql


def sql(source):
    return textwrap.dedent(source).strip("\n") + "\n"


# Exact outputs only where contract v1.2 unambiguously specifies them.
GOLDEN = {
    "right_comment_followed_by_comma": (
        "SELECT id, -- identifier\n name, amount -- final field\nFROM payments;",
        sql("""\
        SELECT
            id -- identifier
            , name
            , amount -- final field
        FROM payments
        ;"""),
    ),
    "comment_above_first_field": (
        "SELECT\n-- identifier\nid FROM users;",
        sql("""\
        SELECT
            -- identifier
            id
        FROM users
        ;"""),
    ),
    "consecutive_comment_lines": (
        "SELECT id,\n-- first\n-- second\nname FROM users;",
        sql("""\
        SELECT
            id
            -- first
            -- second
            , name
        FROM users
        ;"""),
    ),
    "comment_above_join": (
        "SELECT u.id FROM users u\n\n-- payments\nINNER JOIN payments p ON p.user_id=u.id;",
        sql("""\
        SELECT
            u.id
        FROM users u

        -- payments
        INNER JOIN payments p
        ON p.user_id = u.id
        ;"""),
    ),
    "nested_cte_select_from_no_blank": (
        "WITH c AS (SELECT user_id, amount FROM payments) SELECT user_id FROM c;",
        sql("""\
        WITH c AS (
            SELECT
                user_id
                , amount
            FROM payments
        )

        SELECT
            user_id
        FROM c
        ;"""),
    ),
    "join_and_conditions_no_synthetic_true": (
        "SELECT u.id FROM users u JOIN sales s ON u.id=s.user_id AND s.status='OK';",
        sql("""\
        SELECT
            u.id
        FROM users u

        JOIN sales s
        ON u.id = s.user_id
            AND s.status = 'OK'
        ;"""),
    ),
    "where_between_and_is_not_split": (
        "SELECT id FROM t WHERE x BETWEEN 1 AND 5;",
        sql("""\
        SELECT
            id
        FROM t

        WHERE x BETWEEN 1 AND 5
        ;"""),
    ),
    "qualify_two_conditions_no_synthetic_true": (
        "SELECT id FROM t QUALIFY ROW_NUMBER() OVER (PARTITION BY id ORDER BY ts)=1 AND amount>0;",
        sql("""\
        SELECT
            id
        FROM t

        QUALIFY ROW_NUMBER() OVER (
            PARTITION BY id
            ORDER BY ts
        ) = 1
            AND amount > 0
        ;"""),
    ),
    "set_operator_blank_lines": (
        "SELECT id FROM a INTERSECT SELECT id FROM b;",
        sql("""\
        SELECT
            id
        FROM a

        INTERSECT

        SELECT
            id
        FROM b
        ;"""),
    ),
    "literal_whitespace_unchanged": (
        "SELECT 'a  b' AS txt FROM t;",
        sql("""\
        SELECT
            'a  b' AS txt
        FROM t
        ;"""),
    ),
}


class ContractEdgeGoldenTests(unittest.TestCase):
    def test_exact_and_idempotent(self):
        for name, (source, expected) in GOLDEN.items():
            with self.subTest(name=name):
                actual = format_sql(source)
                self.assertEqual(actual, expected)
                self.assertEqual(format_sql(actual), actual)

    def test_same_query_different_whitespace_same_result(self):
        variants = [
            "SELECT id,name FROM users;",
            "  SELECT  id ,  name\n\n  FROM users ;",
            "SELECT\n id\n, name\nFROM users\n;",
        ]
        expected = sql("""\
        SELECT
            id
            , name
        FROM users
        ;""")
        for source in variants:
            with self.subTest(source=source):
                self.assertEqual(format_sql(source), expected)

    def test_no_stdout_side_effect_from_format_sql(self):
        # Direct library calls must not print warnings into stdout.
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            format_sql("SELECT id FROM users;")
        self.assertEqual(buffer.getvalue(), "")


class ContractWarningTests(unittest.TestCase):
    """CLI diagnostics; warnings must not contaminate stdout.

    Current CLI takes an input file path; no new CLI options assumed.
    """

    def run_cli(self, source):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.sql"
            path.write_text(source, encoding="utf-8")
            formatter_script = Path(__file__).resolve().parents[2] / "formatter.py"
            self.assertTrue(formatter_script.is_file(), "Place tests beside formatter.py")
            return subprocess.run(
                [sys.executable, str(formatter_script), str(path)],
                text=True, capture_output=True, encoding="utf-8", check=False,
            )

    def test_ambiguous_comment_warns_and_keeps_text(self):
        source = "SELECT id FROM users\n\n-- ambiguous\n\nWHERE active = 1;"
        completed = self.run_cli(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("SQLFMT-C001", completed.stderr)
        self.assertIn("строк", completed.stderr.lower())
        self.assertIn("-- ambiguous\n\nWHERE", completed.stdout)
        self.assertNotIn("WARNING", completed.stdout)
        self.assertNotIn("SQLFMT-C001", completed.stdout)

    def test_valid_comment_no_ambiguity_warning(self):
        source = "SELECT id FROM users\n\n-- active only\nWHERE active = 1;"
        completed = self.run_cli(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn("SQLFMT-C001", completed.stderr)
        self.assertIn("-- active only\nWHERE", completed.stdout)

    def test_top_level_and_or_warns_without_inserting_true(self):
        source = "SELECT id FROM t WHERE a = 1 AND b = 2 OR c = 3;"
        completed = self.run_cli(source)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(completed.stderr.strip(), "Expected warning for mixed AND/OR")
        self.assertNotIn("WHERE 1=1", completed.stdout)
        self.assertIn("a = 1 AND b = 2 OR c = 3", completed.stdout)
        self.assertNotIn("WARNING", completed.stdout)


if __name__ == "__main__":
    unittest.main()
