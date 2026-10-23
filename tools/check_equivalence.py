"""Reproduce the 73 historical IDs and B10.4 public regression matrix.

Writes hashes/diagnostic codes only. Inputs come from committed synthetic tests.
Run separately for each --root, then compare the JSON objects exactly.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import unittest


def digest(text):
    return hashlib.sha256(text if isinstance(text,bytes) else text.encode()).hexdigest()


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();sys.path.insert(0,str(args.root.resolve()))
    from formatter import format_sql,validate_sql_unchanged
    from dbeaver_adapter import PROFILE_FORMATTERS
    from tests.fixtures.golden import GOLDEN
    from tests.fixtures.edge_cases import GOLDEN as EDGE
    from tests.regression.test_layout_regressions import CASES
    from tests.helpers.fixtures import SYNTHETIC,SIMPLE_INPUT
    from tests.contract.test_diagnostics import REPRO
    from tests.regression import test_layout_corrections as layout
    old=json.loads((args.root/'docs/archive/B104_OUTPUT_CHECK.json').read_text())
    result={'historical':{},'b104':{},'refusals':{}};memo={}
    for key,proof in old.items():
        if ':' in key:
            origin,name=key.split(':')
            source=(EDGE[name][0] if 'edge' in origin else GOLDEN[name][0] if 'golden' in origin else CASES[name])
        else:source={'procedure':SYNTHETIC,'procedure_simple':SIMPLE_INPUT,'procedure_multiline_in':REPRO}[key]
        assert digest(source)==proof['source_sha256'],key
        if source not in memo:
            d1=[];one=format_sql(source,diagnostics=d1);d2=[];two=format_sql(one,diagnostics=d2)
            assert one==two
            validate_sql_unchanged(source,one)
            profiles={}
            for name,fn in PROFILE_FORMATTERS.items():
                raw=fn(source.encode());assert raw==one.encode()
                assert fn(raw)==raw
                profiles[name]=digest(raw)
            memo[source]={'source_sha256':digest(source),'output_sha256':digest(one),'repeat_sha256':digest(two),'diagnostics':[d.code for d in d1],'repeat_diagnostics':[d.code for d in d2],'profiles':profiles}
        result['historical'][key]=memo[source]
        assert memo[source]['output_sha256']==proof['output_sha256'],key
    original=layout.LayoutCorrectionTests.check
    def capture(self,source,expected=None):
        output=original(self,source,expected)
        result['b104'][digest(source)]={'output_sha256':digest(output),'diagnostics':[],'repeat_identical':True}
        return output
    layout.LayoutCorrectionTests.check=capture
    suite=unittest.defaultTestLoader.loadTestsFromModule(layout)
    tested=unittest.TextTestRunner(verbosity=1).run(suite)
    if not tested.wasSuccessful():raise AssertionError('B10.4 matrix failed')
    for source in ('SELECT ROW_NUMBER() OVER win FROM t;', 'SELECT FROM ;',
                   'SELECT a FROM t; -- tail',
                   'SELECT a.id FROM t a JOIN (SELECT id FROM u)\n-- alias\n\nAS b ON a.id=b.id;'):
        ds=[]
        try:
            output=format_sql(source,diagnostics=ds)
            state={'output_sha256':digest(output),'diagnostics':[d.code for d in ds]}
        except Exception as exc:state={'error':type(exc).__name__,'diagnostics':[d.code for d in ds]}
        state['profiles']={name:digest(fn(source.encode())) for name,fn in PROFILE_FORMATTERS.items()}
        result['refusals'][digest(source)]=state
    args.output.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':main()
