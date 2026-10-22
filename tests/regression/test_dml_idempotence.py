"""Standalone INSERT/JOIN and DELETE/literal regressions discovered in B10.1."""
import unittest
from formatter import format_sql

class ExistingDMLReproductionTests(unittest.TestCase):
    """B10.1 defect specimens, upgraded to B10.2a regression assertions."""
    def test_insert_select_with_join_is_idempotent(self):
        sql = 'INSERT INTO example_target SELECT a.id, b.name FROM example_source a INNER JOIN example_other b ON a.id = b.id WHERE a.id IN (1, 2);'
        ds1, ds2 = [], []
        first = format_sql(sql, diagnostics=ds1)
        second = format_sql(first, diagnostics=ds2)
        self.assertEqual(first, second)
        self.assertIn('\nSELECT\n    a.id\n    , b.name\nFROM', first)
        self.assertIn('\n\nINNER JOIN', first)
        self.assertEqual(ds1, [])
        self.assertEqual(ds2, [])

    def test_delete_literal_formats_without_protected_refusal(self):
        sql = "DELETE FROM example_target WHERE id IN (1, 2) AND status = 'OK';"
        ds = []
        actual = format_sql(sql, diagnostics=ds)
        self.assertEqual(actual, "DELETE FROM example_target\n\nWHERE 1=1\n    AND id IN (1, 2)\n    AND status = 'OK'\n;\n")
        self.assertEqual(ds, [])
        self.assertEqual(format_sql(actual, diagnostics=[]), actual)
