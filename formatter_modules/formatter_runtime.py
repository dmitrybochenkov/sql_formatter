"""Project-only SQLFluff parsing with checked original-source coordinates."""
from dataclasses import dataclass
from pathlib import Path

from sqlfluff.core import FluffConfig, Linter

from formatter_modules.formatter_edits import Edit, apply_edits, plan_edits
from formatter_modules.formatter_protection import protected_spans
from formatter_modules.formatter_dialect import select_config

CONFIG_PATH = Path(__file__).resolve().parent.parent / '.sqlfluff'


def project_config():
    # ignore_local_config disables home/appdir, cwd and ancestor discovery.
    return FluffConfig.from_path(
        str(CONFIG_PATH.parent), extra_config_path=str(CONFIG_PATH),
        ignore_local_config=True, overrides={'dialect': 'teradata', 'templater': 'raw'})


@dataclass(frozen=True)
class SourceMap:
    original: str
    normalized: str
    boundaries: tuple[int, ...]

    def __post_init__(self):
        if (len(self.boundaries) != len(self.normalized) + 1 or not self.boundaries
                or self.boundaries[0] != 0 or self.boundaries[-1] != len(self.original)):
            raise ValueError('Invalid source-map boundaries')
        for i, char in enumerate(self.normalized):
            a, b = self.boundaries[i:i + 2]
            if not (0 <= a < b <= len(self.original)) or self.original[a:b].replace(
                    '\r\n', '\n').replace('\r', '\n') != char:
                raise ValueError('Source-map character does not round-trip')

    @classmethod
    def build(cls, source):
        chars, boundaries = [], [0]
        i = 0
        while i < len(source):
            char = source[i]
            if char == '\r':
                i += 2 if source.startswith('\r\n', i) else 1
                chars.append('\n')
            else:
                i += 1
                chars.append(char)
            boundaries.append(i)
        return cls(source, ''.join(chars), tuple(boundaries))

    def original_slice(self, span):
        if span.step not in (None, 1) or not (0 <= span.start <= span.stop <= len(self.normalized)):
            raise ValueError('Invalid normalized source range')
        return slice(self.boundaries[span.start], self.boundaries[span.stop])

    def normalized_offset(self, original_offset):
        # A position inside CRLF is not a valid boundary in the parser view.
        from bisect import bisect_left
        i = bisect_left(self.boundaries, original_offset)
        if i == len(self.boundaries) or self.boundaries[i] != original_offset:
            raise ValueError('Offset splits a CRLF pair or is outside the source')
        return i

    def original_edit(self, edit):
        from dataclasses import replace
        span = self.original_slice(slice(edit.start, edit.end))
        return replace(edit, start=span.start, end=span.stop)


@dataclass(frozen=True)
class OriginalMarker:
    source_slice: slice
    line_no: int


class OriginalSegment:
    """Read-only AST view; never mutate SQLFluff caches or position markers."""
    def __init__(self, node, mapping):
        self._node = node
        self.segments = tuple(OriginalSegment(s, mapping) for s in node.segments)
        marker = node.pos_marker
        self.pos_marker = None
        self.raw = node.raw
        if marker is not None:
            span = mapping.original_slice(marker.source_slice)
            raw = mapping.original[span]
            if not node.is_meta and raw.replace('\r\n', '\n').replace('\r', '\n') != node.raw:
                raise ValueError('SQLFluff AST does not match the normalized source')
            self.pos_marker = OriginalMarker(span, marker.line_no)
            if not node.is_meta:
                self.raw = raw

    @property
    def raw_upper(self):
        return self.raw.upper()

    @property
    def is_code(self):
        return self._node.is_code

    @property
    def is_meta(self):
        return self._node.is_meta

    def is_type(self, *types):
        return self._node.is_type(*types)

    def get_type(self):
        return self._node.get_type()


@dataclass
class ParsedSource:
    tree: object
    config: object
    source_str: str
    violations: list


class SourceLinter:
    def __init__(self):
        self.config = project_config()
        self._linter = Linter(config=self.config)

    def parse_string(self, source):
        mapping = SourceMap.build(source)
        # SQL comments are data, not a second configuration source. Use the
        # public render/parse stages without parse_string's inline directives.
        config = select_config(mapping.normalized, self.config.copy())
        linter = Linter(config=config)
        rendered = linter.render_string(mapping.normalized, '<string>', config, 'utf-8')
        parsed = linter.parse_rendered(rendered)
        tree = parsed.tree
        if tree is not None and tree.raw != mapping.normalized:
            raise ValueError('SQLFluff changed the parser-view source')
        if tree is not None and mapping.normalized != source:
            tree = OriginalSegment(tree, mapping)
        return ParsedSource(tree, parsed.config, source, parsed.violations)


def source_linter():
    return SourceLinter()


def normalize_external_newlines(source):
    """Plan newline edits against the original, never through protected bytes."""
    protected = [(s.start, s.end) for s in protected_spans(source)]
    mapping = SourceMap.build(source)
    edits = []
    for i, char in enumerate(mapping.normalized):
        a, b = mapping.boundaries[i:i + 2]
        if char == '\n' and source[a:b] != '\n' and not any(a < y and b > x for x, y in protected):
            edits.append(mapping.original_edit(Edit(i, i + 1, '\n', 'LINE-ENDINGS',
                                                   'original-source', 'line-endings')))
    accepted, warnings = plan_edits(source, edits, protected=protected)
    if warnings or len(accepted) != len(edits):
        raise ValueError('Cannot atomically normalize external line endings')
    return apply_edits(source, accepted)
