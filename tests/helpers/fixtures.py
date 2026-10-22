"""Synthetic procedure fixtures and lightweight AST doubles shared by tests."""


from dataclasses import dataclass


SYNTHETIC = """REPLACE PROCEDURE example_proc(IN p_start_date DATE, OUT p_count INTEGER)
SQL SECURITY INVOKER
BEGIN
    DECLARE v_cur_date DATE;
    DECLARE v_end_date DATE;
    DECLARE v_count INTEGER DEFAULT 0;
    SET v_cur_date = p_start_date;
    SET v_end_date = p_start_date + 2;
    WHILE v_cur_date <= v_end_date DO
        CALL example_log('Processing; -- DO END', v_cur_date);
        -- Remove previous data
        DELETE FROM example_target WHERE event_date = v_cur_date;
        /* Load current day; END WHILE */
        INSERT INTO example_target
        SELECT a.id, b.name, CASE WHEN c.id IS NULL THEN 'END' ELSE 'DO' END
        FROM example_source a
        INNER JOIN example_other b ON a.id = b.id
        LEFT JOIN example_extra c ON a.id = c.id
        WHERE a.event_date = v_cur_date AND a.status IN (1, 2, 3, 4, 5)
          AND a.id NOT IN (SELECT id FROM example_excluded);
        SET v_cur_date = v_cur_date + 1;
    END WHILE;
    SET p_count = v_count;
END;"""


def wrap(body):
    return 'CREATE PROCEDURE p() BEGIN ' + body + ' END;'


def walk(node):
    yield node
    for child in node.segments:
        yield from walk(child)


SIMPLE_INPUT = "replace procedure P(in D date) sql security invoker begin declare V date; set V=D; while V<D+2 do call LOG_P('DO; END --',V); set V=V+1; end while; end;"


SIMPLE_EXPECTED = """REPLACE PROCEDURE p(
    IN d DATE
)
SQL SECURITY INVOKER
BEGIN
    DECLARE v DATE;

    SET v = d;

    WHILE v < d + 2 DO
        CALL log_p(
            'DO; END --'
            , v
        );

        SET v = v + 1;
    END WHILE;
END;
"""


@dataclass
class Marker:
    source_slice: slice


class Seg:
    def __init__(self, kind, a, b, segments=()):
        self.kind, self.pos_marker, self.segments = kind, Marker(slice(a,b)), segments
    def is_type(self, *types):
        return self.kind in types


def clause(sql, fields, commas):
    return Seg('select_clause', 0, len(sql), [Seg('select_clause_element', *p) for p in fields] + [Seg('comma', *p) for p in commas])
