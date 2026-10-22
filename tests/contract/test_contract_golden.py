"""Exact public SQL contract and CLI guarantees; synthetic fixtures only."""
import unittest

from tests.fixtures.golden import GOLDEN
from formatter import format_sql


class ContractGoldenTests(unittest.TestCase):
    def test_exact_output_and_idempotence(self):
        for name, (source, expected) in GOLDEN.items():
            with self.subTest(case=name):
                actual = format_sql(source)
                self.assertEqual(actual, expected)
                self.assertEqual(format_sql(actual), actual)


    def test_operator_spacing_and_final_newline(self):
        cases = {
            "comparison": ("SELECT id FROM t WHERE amount>=100;", "WHERE amount >= 100\n;\n"),
            "arithmetic": ("SELECT x+y AS total FROM t;", "    x + y AS total\nFROM t\n;\n"),
        }
        for name, (source, expected_suffix) in cases.items():
            with self.subTest(case=name):
                result = format_sql(source)
                self.assertTrue(result.endswith(expected_suffix), repr(result))
                self.assertTrue(result.endswith("\n"))
                self.assertFalse(result.endswith("\n\n"))
                self.assertEqual(format_sql(result), result)

    def test_all_golden_outputs_end_in_single_newline(self):
        for name, (_, expected) in GOLDEN.items():
            with self.subTest(case=name):
                self.assertTrue(expected.endswith("\n"))
                self.assertFalse(expected.endswith("\n\n"))

if __name__ == "__main__":
    unittest.main()
