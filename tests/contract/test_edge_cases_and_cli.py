"""Exact public SQL contract and CLI guarantees; synthetic fixtures only."""
import contextlib
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.fixtures.edge_cases import GOLDEN, sql
from formatter import format_sql




# Exact outputs only where contract v1.2 unambiguously specifies them.


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

    def test_import_preserves_stdout(self):
        project_root = Path(__file__).resolve().parents[2]
        for stream_setup in (
            "io.StringIO()",
            "io.TextIOWrapper(io.BytesIO(), encoding='ascii')",
        ):
            with self.subTest(stream=stream_setup):
                script = (
                    "import io, sys\n"
                    f"stream = {stream_setup}\n"
                    "sys.stdout = stream\n"
                    "encoding = stream.encoding\n"
                    "import formatter\n"
                    "import dbeaver_adapter\n"
                    "assert sys.stdout is stream\n"
                    "assert stream.encoding == encoding\n"
                    "assert stream.tell() == 0\n"
                )
                completed = subprocess.run(
                    [sys.executable, "-c", script], cwd=project_root,
                    capture_output=True, text=True, encoding="utf-8", check=False,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                self.assertEqual(completed.stdout, "")
                self.assertEqual(completed.stderr, "")


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
