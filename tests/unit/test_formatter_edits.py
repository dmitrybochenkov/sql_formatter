"""Stage 1 planner tests; do not require SQLFluff."""
import io
import unittest
from formatter_modules.formatter_edits import Edit, apply_edits, emit_diagnostics, plan_edits


class EditPlannerTests(unittest.TestCase):
    def test_apply_from_right_to_left(self):
        source = 'abcdef'
        edits, warnings = plan_edits(source, [Edit(1, 3, 'X', 'R1'), Edit(4, 6, 'Y', 'R2')])
        self.assertEqual(apply_edits(source, edits), 'aXdY')
        self.assertFalse(warnings)

    def test_overlap_is_reported(self):
        edits, warnings = plan_edits('abcdef', [Edit(1, 4, 'X', 'wide'), Edit(2, 3, 'Y', 'short')])
        self.assertEqual(len(edits), 1)
        self.assertEqual(edits[0].rule_id, 'short')
        self.assertEqual(warnings[0].code, 'SQLFMT-E001')

    def test_protected_span(self):
        edits, warnings = plan_edits('a -- hi\nb', [Edit(2, 7, 'X', 'R')], protected=[(2, 7)])
        self.assertFalse(edits)
        self.assertEqual(warnings[0].code, 'SQLFMT-E002')

    def test_invalid_offsets_raise(self):
        with self.assertRaises(ValueError):
            plan_edits('abc', [Edit(1, 10, '', 'R')])

    def test_diagnostics_only_to_stderr_stream(self):
        _, warnings = plan_edits('abc', [Edit(0, 3, 'X', 'wide'), Edit(1, 2, 'Y', 'short')])
        output = io.StringIO()
        emit_diagnostics(warnings, stream=output)
        self.assertIn('SQLFMT-E001', output.getvalue())


if __name__ == '__main__':
    unittest.main()
