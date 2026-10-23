"""Alternating baseline/candidate measurements in isolated warm processes.

Only synthetic workloads from benchmark_formatter; child paths stay out of JSON.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time

from benchmark_formatter import workloads, summary


def worker(root):
    sys.path.insert(0,str(root.resolve()))
    from formatter import format_sql
    # One warm-up, outside measurements; no shared proof state survives the call.
    format_sql(workloads()['short'],diagnostics=[])
    print('ready',flush=True)
    for line in sys.stdin:
        name=json.loads(line)
        sql=workloads()[name]
        ds=[];start=time.perf_counter();out=format_sql(sql,diagnostics=ds)
        elapsed=time.perf_counter()-start
        print(json.dumps({'seconds':elapsed,'sha256':hashlib.sha256(out.encode()).hexdigest(),
                          'diagnostics':[d.code for d in ds]}),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',type=Path)
    p.add_argument('--candidate',type=Path)
    p.add_argument('--worker',type=Path)
    p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.worker:return worker(args.worker)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1')
    processes={}
    result={'order':['baseline','candidate','candidate','baseline']*2,'warm':{},'cold':{}}
    try:
        for label,root in [('baseline',args.baseline),('candidate',args.candidate)]:
            process=subprocess.Popen([sys.executable,__file__,'--worker',str(root.resolve())],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=env)
            processes[label]=process
            if process.stdout.readline().strip()!='ready':raise RuntimeError('worker initialization failed')
        for name in ('short','insert','procedure_large','procedure_varied'):
            rows={'baseline':[],'candidate':[]};reference=None
            for label in result['order']:
                process=processes[label];process.stdin.write(json.dumps(name)+'\n');process.stdin.flush()
                row=json.loads(process.stdout.readline())
                proof=(row['sha256'],row['diagnostics'])
                if reference is None:reference=proof
                assert proof==reference and not row['diagnostics'], name
                rows[label].append(row['seconds'])
            result['warm'][name]={label:summary(values) for label,values in rows.items()}
            args.output.write_text(json.dumps(result,indent=2)+'\n')
    finally:
        for process in processes.values():
            process.stdin.close();process.wait()
            if process.returncode:raise RuntimeError('benchmark worker failed')
    # Fresh process for import, CLI and official adapter.main with headless selector.
    with tempfile.TemporaryDirectory() as directory:
        sql=Path(directory)/'sample.sql';sql.write_bytes(workloads()['short'].encode())
        for label,root in [('baseline',args.baseline),('candidate',args.candidate)]:
            root=root.resolve();modes={}
            for mode in ('import','cli','adapter'):
                values=[];hashes=[]
                for _ in range(3):
                    if mode=='import':
                        command=[sys.executable,'-c','import sys;sys.path.insert(0,sys.argv[1]);import formatter,dbeaver_adapter',str(root)]
                    elif mode=='cli':command=[sys.executable,str(root/'formatter.py'),str(sql)]
                    else:
                        code='import sys;sys.path.insert(0,sys.argv[1]);import dbeaver_adapter as a;import formatter_modules.profile_selector as s;s.select_profile=lambda:"personal";sys.argv=["dbeaver_adapter.py",sys.argv[2]];raise SystemExit(a.main())'
                        command=[sys.executable,'-c',code,str(root),str(sql)]
                    start=time.perf_counter();completed=subprocess.run(command,cwd=directory,env=env,capture_output=True,check=True)
                    values.append(time.perf_counter()-start)
                    assert not completed.stderr
                    hashes.append(hashlib.sha256(completed.stdout).hexdigest())
                assert len(set(hashes))==1
                modes[mode]={**summary(values),'sha256':hashes[0]}
            result['cold'][label]=modes
    for mode in ('import','cli','adapter'):
        assert result['cold']['baseline'][mode]['sha256']==result['cold']['candidate'][mode]['sha256']
    args.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':main()
