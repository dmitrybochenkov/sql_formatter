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
    group_id: str | None = None


@dataclass(frozen=True)
class Diagnostic:
    code: str
    line: int
    message: str

    def render(self):
        return f"[WARNING] {self.code} | строка {self.line}: {self.message}"


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def edits_overlap(left: Edit, right: Edit) -> bool:
    """Insertions at the same offset or at a replacement start conflict.

    An insertion at a replacement end is safe for right-to-left application.
    """
    if left.start == left.end:
        if right.start == right.end:
            return left.start == right.start
        return right.start <= left.start < right.end
    if right.start == right.end:
        return left.start <= right.start < left.end
    return left.start < right.end and left.end > right.start


def plan_edits(source: str, edits: list[Edit], protected=()):
    """Plan atomic groups, retaining shortest-span priority for single edits.

    A missing group_id means an independent edit. Groups are ordered by their
    shortest member, then its offset; ties retain proposal order. Every group
    is checked in full before any of its edits are accepted.
    """
    protected = tuple(protected)
    groups = {}
    for index, edit in enumerate(edits):
        if not (0 <= edit.start <= edit.end <= len(source)):
            raise ValueError(f"Invalid source range: {edit.rule_id} {edit.start}:{edit.end}")
        if source[edit.start:edit.end] == edit.replacement:
            continue
        key = ("group", edit.group_id) if edit.group_id is not None else ("single", index)
        groups.setdefault(key, []).append(edit)

    accepted = []
    warnings = []
    for group in sorted(groups.values(), key=lambda g: min(
        (e.end - e.start, e.start) for e in g
    )):
        blocked = next((e for e in group if any(
            (e.start < stop and e.end > start)
            or (e.start == e.end and start < e.start < stop)
            for start, stop in protected
        )), None)
        if blocked is not None:
            warnings.append(Diagnostic("SQLFMT-E002", line_number(source, blocked.start),
                                       f"Правка {blocked.rule_id} ({blocked.owner}) затрагивает "
                                       "защищённый участок; вся группа пропущена"))
            continue
        conflict = next((e for i, e in enumerate(group) if any(
            edits_overlap(e, old) for old in accepted + group[:i]
        )), None)
        if conflict is not None:
            warnings.append(Diagnostic("SQLFMT-E001", line_number(source, conflict.start),
                                       f"Конфликт правки {conflict.rule_id} ({conflict.owner}) "
                                       f"[{conflict.start}:{conflict.end}]; вся группа пропущена"))
            continue
        accepted.extend(group)
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
