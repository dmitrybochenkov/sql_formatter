import unittest
from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_protection import protected_spans


class B6SourcePreservationTests(unittest.TestCase):
    def check_source(self,source):
        d1,d2=[],[]
        first=format_sql(source,diagnostics=d1)
        self.assertEqual(format_sql(first,diagnostics=d2).encode(),first.encode())
        validate_sql_unchanged(source,first)
        self.assertEqual([(p.kind,source[p.start:p.end]) for p in protected_spans(source)],
                         [(p.kind,first[p.start:p.end]) for p in protected_spans(first)])
        spans=protected_spans(first)
        self.assertTrue(all(any(p.start<=i<p.end for p in spans) for i,c in enumerate(first) if c=='\r'))
        self.assertFalse(any(d.code=='SQLFMT-E003' for d in d1+d2))
        return first,d1,d2

    def test_literals_identifiers_and_comments(self):
        for ending in ('\n','\r\n','\r'):
            for value in ('x\ny','x\r\ny','x\ry','x\r\ny\rz\nw'):
                source=f"SELECT{ending}'{value}' AS \"{value}\",{ending}a /* {value} */ FROM t;{ending}"
                with self.subTest(ending=repr(ending),value=repr(value)):
                    self.check_source(source)

    def test_line_comments_and_empty_lines(self):
        for ending in ('\n','\r\n','\r'):
            source=f'SELECT a -- keep{ending}FROM t{ending}{ending}WHERE a=1;{ending}'
            actual,d1,d2=self.check_source(source)
            self.assertEqual(actual,'SELECT\n    a -- keep\nFROM t\n\nWHERE a = 1\n;\n')
            self.assertEqual(d1+d2,[])

    def test_strict_validator_detects_protected_cr_changes(self):
        for value in ('x\r\ny','x\ry'):
            for source in (f"SELECT '{value}' FROM t;",f'SELECT "{value}" FROM t;',
                           f'SELECT a /* {value} */ FROM t;'):
                result=format_sql(source,diagnostics=[])
                for invalid in (result.replace('\r\n','\n').replace('\r','\n'),
                                result.replace('\r',''), result.replace('\r','\r\r')):
                    with self.subTest(source=source,invalid=invalid),self.assertRaises(ValueError):
                        validate_sql_unchanged(source,invalid)

    def test_protected_sequence_type_count_and_order(self):
        source="SELECT 'a', 'b' AS \"c\" /* one */ FROM t /* two */;"
        for invalid in (source.replace("'a'", "'b'", 1),
                        source.replace('/* one */',''),
                        source.replace('/* one */','/* one */ /* one */'),
                        source.replace('/* one */','/* swap */').replace('/* two */','/* one */').replace('/* swap */','/* two */'),
                        source.replace('\"c\"', "'c'")):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):
                validate_sql_unchanged(source,invalid)

    def test_detached_comment_diagnostics_are_real_refusals(self):
        source='SELECT SUM(a) OVER (PARTITION BY a,\r\n-- detached\r\n\r\nb) AS n FROM t;'
        first,d1,d2=self.check_source(source)
        self.assertIn('a,\n-- detached\n\nb',first)
        for diagnostics in (d1,d2):
            self.assertTrue(any(d.code=='SQLFMT-C001' for d in diagnostics))
            self.assertTrue(any(d.code=='SQLFMT-E002' and 'SELECT-BLANKLINES' in d.message for d in diagnostics))

    def test_named_window_refusal_preserves_even_external_endings(self):
        source='SELECT SUM(a) OVER w\r\nFROM t;\r'
        d1,d2=[],[]
        self.assertEqual(format_sql(source,diagnostics=d1),source)
        self.assertEqual(format_sql(source,diagnostics=d2),source)
        self.assertEqual([d.code for d in d1],['SQLFMT-E004'])
        self.assertEqual(d1,d2)
