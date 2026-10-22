import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from formatter import format_sql, validate_sql_unchanged
from formatter_modules.formatter_runtime import CONFIG_PATH
from tests.helpers.runners import adapter_command


class B6ContractTests(unittest.TestCase):
    def test_all_supported_constructs_share_canonical_lf(self):
        from tests.fixtures.golden import GOLDEN
        from tests.fixtures.edge_cases import GOLDEN as EDGE
        cases=[GOLDEN[k] for k in ('ctes_separated','union_all','window_multiple_keys','qualify')]
        cases += [EDGE['nested_cte_select_from_no_blank']]
        cases += [('SELECT a FROM t WHERE a IN (SELECT b FROM u);',
                   'SELECT\n    a\nFROM t\n\nWHERE a IN (\n    SELECT\n        b\n    FROM u\n)\n;\n')]
        for source,expected in cases:
            # Vary only physical line endings of the established LF fixture.
            # Arbitrary breaks inside expressions are separate pre-existing debt.
            for layout in (expected, source.replace('SELECT ', 'SELECT\n', 1) + '\n'):
                tokens=layout.split('\n')
                for endings in (['\n'],['\r\n'],['\r'],['\n','\r\n','\r']):
                    variant=''.join(t+(endings[i%len(endings)] if i<len(tokens)-1 else '') for i,t in enumerate(tokens))
                    with self.subTest(source=source,endings=endings,layout=layout):
                        d1,d2=[],[]
                        first=format_sql(variant,diagnostics=d1)
                        self.assertEqual(first,expected)
                        self.assertEqual(format_sql(first,diagnostics=d2),first)
                        validate_sql_unchanged(variant,first)
                        self.assertEqual(d1+d2,[])

    def test_cli_reads_exact_bytes_before_formatter(self):
        import formatter as cli
        source="SELECT 'x\r\ny' /* c\rd */\r\nFROM t;\r"
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'input.sql';path.write_bytes(source.encode())
            import io
            output=io.TextIOWrapper(io.BytesIO(),encoding='utf-8')
            with patch.object(sys,'argv',['formatter.py',str(path)]),patch.object(sys,'stdout',output), \
                 patch.object(cli,'format_sql',return_value=source) as engine:
                self.assertIsNone(cli.main())
                engine.assert_called_once_with(source, diagnostics=[])
                output.flush()
                self.assertEqual(output.buffer.getvalue(),source.encode())

    def test_cwd_foreign_configuration_and_cli(self):
        root=CONFIG_PATH.parent
        source="SELECT 'x\r\ny' AS a /* c\rd */\r\nFROM t;\r"
        expected=format_sql(source,diagnostics=[]).encode()
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);cwd=base/'other';cwd.mkdir()
            foreign='[sqlfluff]\ndialect = ansi\ntemplater = jinja\nmax_line_length = 9\n'
            (base/'.sqlfluff').write_text(foreign);(cwd/'.sqlfluff').write_text(foreign)
            path=base/'input.sql';path.write_bytes(source.encode())
            env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
            for directory in (root,cwd):
                for script in ('dbeaver_adapter.py','formatter.py'):
                    command = adapter_command(root/script,path) if script=='dbeaver_adapter.py' else [sys.executable,str(root/script),str(path)]
                    result=subprocess.run(command,cwd=directory,env=env,capture_output=True)
                    self.assertEqual(result.returncode,0,result.stderr)
                    self.assertEqual(result.stdout,expected)
                    self.assertEqual(result.stderr,b'')
                code='import sys,json;sys.path.insert(0,sys.argv[1]);from formatter_modules.formatter_runtime import source_linter; c=source_linter().config;print(json.dumps([c.get("dialect"),c.get("templater"),c.get("max_line_length")]))'
                result=subprocess.run([sys.executable,'-c',code,str(root)],cwd=directory,env=env,capture_output=True,check=True)
                self.assertEqual(json.loads(result.stdout),['teradata','raw',120])
