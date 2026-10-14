import unittest
from unittest.mock import patch

from formatter_modules.formatter_runtime import SourceMap, source_linter, normalize_external_newlines
from formatter_modules.formatter_edits import Edit, plan_edits, apply_edits
from formatter_modules.formatter_protection import protected_spans


class SourceMapTests(unittest.TestCase):
    def test_boundaries_and_round_trip(self):
        for source in ('', 'a\nb', 'a\r\nb', 'a\rb', '\r\n\r\n\r\n', "é\r\n'中\r🙂'\nx"):
            with self.subTest(source=source):
                mapping = SourceMap.build(source)
                self.assertEqual(mapping.normalized, source.replace('\r\n','\n').replace('\r','\n'))
                restored = ''.join(source[mapping.original_slice(slice(i,i+1))]
                                   for i in range(len(mapping.normalized)))
                self.assertEqual(restored.encode(), source.encode())
                for i, original in enumerate(mapping.boundaries):
                    self.assertEqual(mapping.normalized_offset(original), i)

    def test_invalid_boundaries_fail_closed(self):
        mapping = SourceMap.build('a\r\nb')
        for offset in (-1,2,5):
            with self.assertRaises(ValueError):
                mapping.normalized_offset(offset)
        for span in (slice(-1,2),slice(2,1),slice(0,5),slice(0,2,2)):
            with self.assertRaises(ValueError):
                mapping.original_slice(span)
        for args in [('x','x',(0,2)), ('\r\n','\n',(0,1)), ('ab','xy',(0,1,2))]:
            with self.assertRaises(ValueError):
                SourceMap(*args)

    def test_ast_positions_and_raw_are_original(self):
        source = "SELECT\r\n'x\r\ny' AS \"a\rb\" /* c\rd */\rFROM t;"
        tree = source_linter().parse_string(source).tree
        self.assertEqual(tree.raw,source)
        def check(node):
            if node.pos_marker and not node.is_meta:
                self.assertEqual(source[node.pos_marker.source_slice],node.raw)
            for child in node.segments:
                check(child)
        check(tree)

    def test_edits_touching_protected_boundaries(self):
        source = "SELECT\r\n'a\r\nb'\rFROM t;"
        mapping = SourceMap.build(source)
        span = protected_spans(source)[0]
        start,end = mapping.normalized_offset(span.start),mapping.normalized_offset(span.end)
        edits = [mapping.original_edit(Edit(start,start,' ', 'before', group_id='g')),
                 mapping.original_edit(Edit(end,end,' ', 'after', group_id='g'))]
        accepted,warnings = plan_edits(source,edits,[(span.start,span.end)])
        self.assertEqual(warnings,[])
        self.assertEqual(apply_edits(source,accepted),source[:span.start]+' '+source[span.start:span.end]+' '+source[span.end:])
        blocked = mapping.original_edit(Edit(start+1,start+1,'X','inside',group_id='g'))
        accepted,warnings = plan_edits(source,edits+[blocked],[(span.start,span.end)])
        self.assertEqual(accepted,[])
        self.assertEqual([w.code for w in warnings],['SQLFMT-E002'])

    def test_mapped_conflicts_remain_atomic(self):
        source='SELECT\r\na FROM t;';mapping=SourceMap.build(source)
        edits=[mapping.original_edit(Edit(6,7,'\n    ','gap',group_id='g')),
               mapping.original_edit(Edit(7,7,' ','insert',group_id='g'))]
        # Two unrelated inserts at one boundary compete; the group is all-or-none.
        competitor=mapping.original_edit(Edit(7,7,'  ','other'))
        accepted,warnings=plan_edits(source,[competitor]+edits)
        self.assertIn(len([e for e in accepted if e.group_id=='g']),(0,2))
        self.assertTrue(any(w.code=='SQLFMT-E001' for w in warnings))
        accepted,warnings=plan_edits(source,edits)
        reverse,_=plan_edits(source,list(reversed(edits)))
        self.assertFalse(warnings)
        self.assertEqual(apply_edits(source,accepted),apply_edits(source,reverse))

    def test_external_normalization_and_line_comment_terminators(self):
        source="SELECT\r\n'a\r\nb',\"c\rd\" /* e\r\nf */ -- keep\rFROM t;\r"
        expected="SELECT\n'a\r\nb',\"c\rd\" /* e\r\nf */ -- keep\nFROM t;\n"
        self.assertEqual(normalize_external_newlines(source),expected)
        self.assertEqual(normalize_external_newlines(expected),expected)
        self.assertEqual([(p.kind,source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind,expected[p.start:p.end]) for p in protected_spans(expected)])

    def test_config_does_not_discover_home_or_cwd(self):
        with patch('sqlfluff.core.config.loader._load_user_appdir_config',side_effect=AssertionError('appdir')) as appdir, \
             patch('sqlfluff.core.config.loader.load_config_at_path',side_effect=AssertionError('home/cwd')) as local:
            config=source_linter().config
        appdir.assert_not_called();local.assert_not_called()
        self.assertEqual(config.get('dialect'),'teradata')
        self.assertEqual(config.get('templater'),'raw')
        self.assertEqual(config.get('max_line_length'),120)

    def test_inline_config_comments_are_data(self):
        source="-- sqlfluff:templater:jinja\n-- sqlfluff:dialect:ansi\nSELECT '{{ 1+1 }}' FROM t;"
        parsed=source_linter().parse_string(source)
        self.assertEqual(parsed.config.get('templater'),'raw')
        self.assertEqual(parsed.config.get('dialect'),'teradata')
        self.assertEqual(parsed.tree.raw,source)

    def test_diagnostic_lines_count_all_physical_endings(self):
        from formatter_modules.formatter_edits import line_number
        source="SELECT 'x\ry' /* a\r\nb */\nFROM t;"
        self.assertEqual(line_number(source,source.index('FROM')),4)
        span=protected_spans(source)[1]
        _,warnings=plan_edits(source,[Edit(span.start+6,span.start+6,'X','inside')],[(span.start,span.end)])
        self.assertEqual(warnings[0].line,3)
