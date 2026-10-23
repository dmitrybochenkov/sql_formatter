"""Synthetic, headless benchmark. No user SQL and no GUI; output is JSON metadata.

Run with the same interpreter against --root BASELINE and --root CANDIDATE.
The root path is not persisted in results. cProfile measurements are separate
from wall-clock samples; cumulative profiler rows must not be summed.
"""
import argparse
import cProfile
import hashlib
import json
import platform
import statistics
import sys
import time
from pathlib import Path


def workloads():
    dml = "INSERT INTO target SELECT a.id, SUM(b.amount) AS total FROM source_a a LEFT JOIN (SELECT id, amount FROM source_b) b ON a.id=b.id WHERE a.id NOT IN (1,2,3,4,5) AND b.amount>0 GROUP BY a.id HAVING SUM(b.amount)>1 AND COUNT(*)>0;"
    return {
        'short': 'select id, name from users where active=1;',
        'joins': 'SELECT a.id FROM t a JOIN u b ON a.id=b.id LEFT JOIN v c ON b.id=c.id AND c.x>0;',
        'cte': 'WITH x AS (SELECT id FROM t WHERE a=1 AND b=2) SELECT id FROM x WHERE id IN (SELECT id FROM u);',
        'in_lists': 'SELECT id FROM t WHERE id IN (1,2,3,4,5) AND id NOT IN (6,7,8,9);',
        'clauses': 'SELECT id, SUM(x) AS total FROM t WHERE x>0 GROUP BY id HAVING SUM(x)>1 AND COUNT(*)>0 QUALIFY ROW_NUMBER() OVER (ORDER BY id)=1 ORDER BY id;',
        'insert': dml,
        'statements': 'SELECT id FROM t; UPDATE t SET id=1; DELETE FROM u WHERE id=2;',
        'procedure_short': 'CREATE PROCEDURE sample_proc() BEGIN DECLARE n INTEGER; SET n=1; INSERT INTO target SELECT id FROM source_a; END;',
        'procedure_varied': 'CREATE PROCEDURE varied_proc(IN lim INTEGER) BEGIN '+''.join(dml.replace('b.amount>0', 'b.amount>'+str(i)) for i in range(5))+' END;',
        'procedure_large': 'REPLACE PROCEDURE sample_proc(IN lim INTEGER) SQL SECURITY INVOKER BEGIN DECLARE n INTEGER; SET n=0; WHILE n<lim DO '+dml*3+' BEGIN '+dml+' END; SET n=n+1; END WHILE; '+dml+' END;',
    }


def summary(values):
    return {'samples_s': values, 'median_s': statistics.median(values),
            'min_s': min(values), 'max_s': max(values), 'spread_s': max(values)-min(values)}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--cases',nargs='*')
    p.add_argument('--profile-costs',action='store_true')
    args=p.parse_args()
    if args.repeats<2: p.error('at least two repeats are required')
    sys.path.insert(0,str(args.root.resolve()))
    start=time.perf_counter()
    from formatter import format_sql
    from dbeaver_adapter import PROFILE_FORMATTERS
    import sqlfluff
    imported=time.perf_counter()-start
    result={'python':platform.python_version(),'platform':platform.system(),
            'sqlfluff':sqlfluff.__version__,'import_s':imported,'cases':{}}
    for name,sql in workloads().items():
        if args.cases and name not in args.cases: continue
        ds=[];start=time.perf_counter();canonical=format_sql(sql,diagnostics=ds)
        first=time.perf_counter()-start
        if ds: raise AssertionError((name,'unexpected diagnostics'))
        row={'characters':len(sql),'first_in_process_s':first,'measurements':{},'sha256':hashlib.sha256(canonical.encode()).hexdigest()}
        for mode in ('engine','repeat','personal','corporate'):
            values=[]
            for _ in range(args.repeats):
                start=time.perf_counter()
                if mode in ('engine','repeat'):
                    diagnostics=[];out=format_sql(canonical if mode=='repeat' else sql,diagnostics=diagnostics)
                    assert not diagnostics
                else: out=PROFILE_FORMATTERS[mode](sql.encode()).decode()
                values.append(time.perf_counter()-start)
                assert out==canonical,(name,mode,'output mismatch')
            row['measurements'][mode]=summary(values)
        result['cases'][name]=row
        args.output.write_text(json.dumps(result,indent=2)+'\n')
    if args.profile_costs:
        prof=cProfile.Profile()
        prof.enable();format_sql(workloads()['procedure_large'],diagnostics=[]);prof.disable()
        rows=[]
        for entry in prof.getstats():
            code=entry.code
            if isinstance(code,str): continue
            file=Path(code.co_filename).name
            rows.append({'file':file,'function':code.co_name,'qualified_function':code.co_qualname,'calls':entry.callcount,
                         'self_s':entry.inlinetime,'cumulative_s':entry.totaltime})
        result['profile']=sorted(rows,key=lambda x:x['cumulative_s'],reverse=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__': main()
