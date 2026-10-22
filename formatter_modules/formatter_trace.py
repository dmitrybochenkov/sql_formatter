"""Explicit opt-in, metadata-only tracing. Never writes to process streams."""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
from time import perf_counter


STAGES = frozenset({
    'read', 'profile', 'decode', 'adapter_format', 'adapter_validate',
    'normalize', 'parse', 'layout', 'layout_gap', 'layout_boundary', 'layout_list',
    'dml', 'planner', 'case', 'validate', 'repeat', 'rollback', 'result', 'diagnostic_run',
})
CODES = frozenset({'START','END','ERROR','UNPARSABLE','LEXICAL_ERROR',
    'NON_WHITESPACE','COMMENT_ATTACHMENT','CHANGED','UNCHANGED','NON_IDEMPOTENT','REPEAT_DIAGNOSTIC',
    'SQLFMT-C001','SQLFMT-E001','SQLFMT-E002','SQLFMT-E003','SQLFMT-E004','SQLFMT-W001'})
SEGMENTS = frozenset({'unparsable','procedure_definition','procedure_block',
    'procedure_executable','procedure_assignment','procedure_call','procedure_while',
    'procedure_parameter','procedure_declaration','bracketed','insert_statement',
    'delete_statement','select_statement','where_clause','join_clause'})


def event(stage, code='END', *, node=None, position=None, elapsed=None, view=None, error_type=None):
    if os.environ.get('SQL_FORMATTER_TRACE') != '1':
        return
    try:
        # All strings are allowlisted: SQLFluff exceptions and AST.raw never enter logs.
        if stage not in STAGES or code not in CODES:
            return
        record={'time':datetime.now(timezone.utc).isoformat(), 'pid':os.getpid(),
                'stage':stage,'code':code}
        if node is not None:
            kind=node.get_type()
            record['segment']=kind if kind in SEGMENTS else 'other'
            if node.pos_marker is not None:
                if view in (None,'original'):
                    record['line']=int(node.pos_marker.line_no)
                if position is None:
                    position=node.pos_marker.source_slice.start
        if position is not None:
            record['offset']=int(position)
        if view in ('original', 'candidate', 'repeat'):
            record['view']=view
        if error_type is not None:
            record['error_type']=error_type if error_type in {
                'ValueError','TypeError','ImportError','PermissionError','OSError',
                'RuntimeError','ProcedureRefusal','SQLParseError'} else 'Exception'
        if elapsed is not None:
            record['elapsed_ms']=round(float(elapsed)*1000,3)
        directory=Path(os.environ.get('SQL_FORMATTER_LOG_DIR') or
            str(Path(os.environ.get('LOCALAPPDATA') or tempfile.gettempdir())/'SQLFormatter'/'logs'))
        directory.mkdir(parents=True,exist_ok=True)
        with (directory/'diagnostic.jsonl').open('a',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(record)+'\n')
    except Exception:
        pass  # Diagnostics cannot change the SQL result, even if the disk is unavailable.


@contextmanager
def stage(name, *, node=None):
    enabled=os.environ.get('SQL_FORMATTER_TRACE') == '1'
    if not enabled:
        yield
        return
    start=perf_counter()
    event(name,'START',node=node)
    try:
        yield
    except BaseException as exc:
        event(name,'ERROR',node=node,elapsed=perf_counter()-start,error_type=type(exc).__name__)
        raise
    else:
        event(name,'END',node=node,elapsed=perf_counter()-start)
