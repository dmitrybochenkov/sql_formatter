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

    def test_group_is_applied_as_a_unit(self):
        edits = [Edit(1, 2, '', 'MOVE', group_id='move'),
                 Edit(4, 4, ',', 'MOVE', group_id='move')]
        planned, warnings = plan_edits('a, b', edits)
        self.assertEqual(apply_edits('a, b', planned), 'a b,')
        self.assertFalse(warnings)

    def test_protected_member_rejects_entire_group(self):
        edits = [Edit(1, 2, '', 'MOVE', group_id='move'),
                 Edit(3, 3, ',', 'MOVE', group_id='move'),
                 Edit(0, 1, 'A', 'INDEPENDENT')]
        planned, warnings = plan_edits('a, b', edits, protected=[(2, 4)])
        self.assertEqual(apply_edits('a, b', planned), 'A, b')
        self.assertEqual([w.code for w in warnings], ['SQLFMT-E002'])

    def test_conflicting_member_rejects_entire_group(self):
        edits = [Edit(0, 2, 'A', 'GROUP', group_id='g'),
                 Edit(4, 6, 'B', 'GROUP', group_id='g'),
                 Edit(1, 2, 'X', 'SHORT')]
        planned, warnings = plan_edits('abcdef', edits)
        self.assertEqual(apply_edits('abcdef', planned), 'aXcdef')
        self.assertEqual([w.code for w in warnings], ['SQLFMT-E001'])

    def test_internal_overlap_rejects_group(self):
        for edits in ([Edit(0, 3, 'A', 'G', group_id='g'),
                       Edit(1, 2, 'B', 'G', group_id='g')],
                      [Edit(1, 1, 'A', 'G', group_id='g'),
                       Edit(1, 1, 'B', 'G', group_id='g')]):
            with self.subTest(edits=edits):
                planned, warnings = plan_edits('abc', edits)
                self.assertEqual(planned, [])
                self.assertEqual(warnings[0].code, 'SQLFMT-E001')

    def test_same_position_insertions_conflict(self):
        # Equal-priority independent proposals retain their input order.
        edits = [Edit(1, 1, 'X', 'FIRST'), Edit(1, 1, 'Y', 'SECOND')]
        planned, warnings = plan_edits('ab', edits)
        self.assertEqual(apply_edits('ab', planned), 'aXb')
        self.assertEqual(warnings[0].code, 'SQLFMT-E001')

    def test_same_position_conflict_rolls_back_group(self):
        edits = [Edit(1, 1, 'X', 'FIRST'),
                 Edit(1, 1, 'Y', 'G', group_id='g'),
                 Edit(2, 3, '', 'G', group_id='g')]
        planned, warnings = plan_edits('abc', edits)
        self.assertEqual(apply_edits('abc', planned), 'aXbc')
        self.assertEqual(warnings[0].code, 'SQLFMT-E001')

    def test_disjoint_groups_apply_right_to_left_in_any_proposal_order(self):
        edits = [Edit(0, 1, 'LONG', 'G', group_id='g'),
                 Edit(5, 6, 'Z', 'G', group_id='g'), Edit(2, 3, 'X', 'S')]
        for proposals in (edits, list(reversed(edits))):
            planned, warnings = plan_edits('abcdef', proposals)
            self.assertEqual(apply_edits('abcdef', planned), 'LONGbXdeZ')
            self.assertFalse(warnings)

    def test_insertion_at_replacement_boundaries(self):
        planned, warnings = plan_edits('abcd', [Edit(1, 2, 'B', 'R'),
                                                Edit(2, 2, 'X', 'END')])
        self.assertEqual(apply_edits('abcd', planned), 'aBXcd')
        self.assertFalse(warnings)
        planned, warnings = plan_edits('abcd', [Edit(1, 2, 'B', 'R'),
                                                Edit(1, 1, 'X', 'START')])
        self.assertEqual(apply_edits('abcd', planned), 'aXbcd')
        self.assertEqual(warnings[0].code, 'SQLFMT-E001')

    def test_noop_does_not_block_real_edit(self):
        planned, warnings = plan_edits('abc', [Edit(1, 2, 'b', 'NOOP'),
                                               Edit(0, 3, 'ABC', 'REAL')])
        self.assertEqual(apply_edits('abc', planned), 'ABC')
        self.assertFalse(warnings)


if __name__ == '__main__':
    unittest.main()
