"""Safe source-span edits and diagnostics for the Teradata formatter.

Offsets are Python string offsets into the *same* source snapshot. This module
is intentionally independent of SQLFluff so it can be unit-tested offline.
"""
from dataclasses import dataclass
import sys


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: str
    rule_id: str
    owner: str = ""


@dataclass(frozen=True)
class Diagnostic:
    code: str
    line: int
    message: str

    def render(self):
        return f"[WARNING] {self.code} | строка {self.line}: {self.message}"


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def plan_edits(source: str, edits: list[Edit], protected=()):
    """Return accepted edits and diagnostics; never silently drop overlaps.

    Preserve the legacy shortest-span priority during the transition. The
    formatter's later stages must be migrated to this planner incrementally.
    """
    protected = tuple(protected)
    accepted = []
    warnings = []
    for edit in sorted(edits, key=lambda e: (e.end - e.start, e.start)):
        if not (0 <= edit.start <= edit.end <= len(source)):
            raise ValueError(f"Invalid source range: {edit.rule_id} {edit.start}:{edit.end}")
        if any(edit.start < stop and edit.end > start for start, stop in protected):
            warnings.append(Diagnostic("SQLFMT-E002", line_number(source, edit.start),
                                       f"Правка {edit.rule_id} затрагивает защищённый участок; пропущена"))
            continue
        if any(edit.start < old.end and edit.end > old.start for old in accepted):
            warnings.append(Diagnostic("SQLFMT-E001", line_number(source, edit.start),
                                       f"Конфликт правки {edit.rule_id} ({edit.owner}); пропущена"))
            continue
        accepted.append(edit)
    return accepted, warnings


def apply_edits(source: str, edits: list[Edit]) -> str:
    result = source
    for edit in sorted(edits, key=lambda e: e.start, reverse=True):
        result = result[:edit.start] + edit.replacement + result[edit.end:]
    return result


def emit_diagnostics(diagnostics, stream=None):
    stream = sys.stderr if stream is None else stream
    for diagnostic in diagnostics:
        print(diagnostic.render(), file=stream)
