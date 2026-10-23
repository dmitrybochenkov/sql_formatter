"""One synthetic instrumented run; NOT a production latency benchmark."""
import argparse
import cProfile
import json
import os
import hashlib
import subprocess
from pathlib import Path
import sys
import tempfile
from time import perf_counter
from benchmark_formatter import workloads


def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--adapter-only',action='store_true')
    args=p.parse_args();sys.path.insert(0,str(args.root.resolve()))
    if args.adapter_only:
        with tempfile.TemporaryDirectory() as directory:
            source=Path(directory)/'sample.sql'
            source.write_bytes(workloads()['short'].encode())
            env=dict(os.environ,SQL_FORMATTER_TRACE='1',SQL_FORMATTER_LOG_DIR=directory,
                     PYTHONDONTWRITEBYTECODE='1')
            code='import sys;sys.path.insert(0,sys.argv[1]);import dbeaver_adapter as a;import formatter_modules.profile_selector as s;s.select_profile=lambda:"personal";sys.argv=["dbeaver_adapter.py",sys.argv[2]];raise SystemExit(a.main())'
            start=perf_counter()
            completed=subprocess.run([sys.executable,'-c',code,str(args.root.resolve()),str(source)],
                                     env=env,cwd=directory,capture_output=True,check=True)
            elapsed=perf_counter()-start
            assert not completed.stderr
            trace=[json.loads(line) for line in (Path(directory)/'diagnostic.jsonl').read_text().splitlines()]
            trace=[{k:v for k,v in row.items() if k not in ('time','pid')} for row in trace]
            args.output.write_text(json.dumps({'elapsed_s':elapsed,
                'stdout_sha256':hashlib.sha256(completed.stdout).hexdigest(),
                'stderr_bytes':len(completed.stderr),'trace':trace},indent=2)+'\n')
        return
    from formatter import format_sql
    with tempfile.TemporaryDirectory() as directory:
        os.environ['SQL_FORMATTER_TRACE']='1';os.environ['SQL_FORMATTER_LOG_DIR']=directory
        prof=cProfile.Profile();start=perf_counter();prof.enable()
        format_sql(workloads()['procedure_large'],diagnostics=[])
        prof.disable();elapsed=perf_counter()-start
        rows=[]
        for item in prof.getstats():
            code=item.code
            if isinstance(code,str):continue
            if not Path(code.co_filename).name.startswith('formatter') and Path(code.co_filename).name not in ('fluffconfig.py','linter.py','parser.py','lexer.py','teradata_procedure_grammar.py'):continue
            rows.append({'file':Path(code.co_filename).name,'function':code.co_qualname,'calls':item.callcount,'self_s':item.inlinetime,'cumulative_s':item.totaltime})
        trace=[json.loads(line) for line in (Path(directory)/'diagnostic.jsonl').read_text().splitlines()]
        # Strip timestamps and pids; metadata only. Inclusive parents overlap.
        trace=[{k:v for k,v in row.items() if k not in ('time','pid')} for row in trace]
        args.output.write_text(json.dumps({'instrumented_s':elapsed,'profile':rows,'trace':trace},indent=2)+'\n')

if __name__=='__main__':main()
