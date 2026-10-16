"""B10.1 grammar, reused by the explicit B10.2 runtime/case selector.

No dialect registry mutation, installed-library patches, formatting or linting.
parse_procedure() remains the isolated LF-only diagnostic entry point.
SQLFluff 4.4.0 only.
"""
from dataclasses import dataclass

import sqlfluff
from sqlfluff.core import FluffConfig
from sqlfluff.core.dialects import load_raw_dialect
from sqlfluff.core.parser import (
    AnyNumberOf, BaseSegment, Bracketed, Delimited, Lexer, OneOf,
    Parser, Ref, Sequence,
)
from sqlfluff.core.parser.segments import BaseFileSegment


class ProcedureParameterSegment(BaseSegment):
    type = 'procedure_parameter'
    match_grammar = Sequence(
        OneOf('IN', 'OUT', 'INOUT', optional=True),
        Ref('SingleIdentifierGrammar'), Ref('DatatypeSegment'),
    )


class ProcedureSecuritySegment(BaseSegment):
    type = 'procedure_security'
    match_grammar = Sequence('SQL', 'SECURITY', 'INVOKER')


class ProcedureDeclareSegment(BaseSegment):
    type = 'procedure_declaration'
    match_grammar = Sequence(
        'DECLARE', Delimited(Ref('SingleIdentifierGrammar')),
        Ref('DatatypeSegment'),
        Sequence('DEFAULT', Ref('LiteralGrammar'), optional=True),
    )


class ProcedureSetSegment(BaseSegment):
    type = 'procedure_assignment'
    match_grammar = Sequence(
        'SET', Ref('SingleIdentifierGrammar'), Ref('EqualsSegment'),
        Ref('ExpressionSegment'),
    )


class ProcedureCallSegment(BaseSegment):
    type = 'procedure_call'
    match_grammar = Sequence(
        'CALL', Ref('ObjectReferenceSegment'),
        Bracketed(Delimited(Ref('ExpressionSegment'), optional=True)),
    )


class ProcedureWhileSegment(BaseSegment):
    type = 'procedure_while'
    match_grammar = Sequence(
        'WHILE', Ref('ExpressionSegment', terminators=['DO']), 'DO',
        AnyNumberOf(Ref('ProcedureExecutableSegment'), min_times=1),
        'END', 'WHILE', reset_terminators=True,
    )


class ProcedureBlockSegment(BaseSegment):
    type = 'procedure_block'
    match_grammar = Sequence(
        'BEGIN',
        AnyNumberOf(Sequence(Ref('ProcedureDeclareSegment'), Ref('SemicolonSegment'))),
        AnyNumberOf(Ref('ProcedureExecutableSegment')),
        'END', reset_terminators=True,
    )


class ProcedureExecutableSegment(BaseSegment):
    type = 'procedure_executable'
    match_grammar = Sequence(
        OneOf(
            Ref('ProcedureSetSegment'), Ref('ProcedureCallSegment'),
            Ref('ProcedureWhileSegment'), Ref('ProcedureBlockSegment'),
            # Bound inherited DML grammars before the next procedural statement.
            Ref('DeleteStatementSegment', terminators=[Ref('SemicolonSegment')]),
            Ref('InsertStatementSegment', terminators=[Ref('SemicolonSegment')]),
        ),
        Ref('SemicolonSegment'), reset_terminators=True,
    )


class ProcedureDefinitionSegment(BaseSegment):
    type = 'procedure_definition'
    match_grammar = Sequence(
        OneOf('CREATE', 'REPLACE'), 'PROCEDURE', Ref('ObjectReferenceSegment'),
        Bracketed(Delimited(Ref('ProcedureParameterSegment'), optional=True)),
        Ref('ProcedureSecuritySegment', optional=True), Ref('ProcedureBlockSegment'),
        reset_terminators=True,
    )


class ProcedureFileSegment(BaseFileSegment):
    match_grammar = Sequence(
        Ref('ProcedureDefinitionSegment'), Ref('SemicolonSegment'),
        reset_terminators=True,
    )


@dataclass(frozen=True)
class ProcedureParse:
    tree: BaseFileSegment
    violations: tuple

    @property
    def complete(self):
        return not self.violations and not any(self.tree.recursive_crawl('unparsable'))


def prototype_config(base_config=None):
    """Create a private expanded dialect; never register it globally."""
    if sqlfluff.__version__ != '4.4.0':
        raise RuntimeError('Procedure prototype requires SQLFluff 4.4.0')
    dialect = load_raw_dialect('teradata').copy_as('teradata_procedure_prototype')
    dialect.sets('unreserved_keywords').update(
        {'PROCEDURE', 'INOUT', 'SECURITY', 'INVOKER', 'DECLARE', 'WHILE', 'DO', 'CALL'}
    )
    dialect.add(**{cls.__name__: cls for cls in (
        ProcedureParameterSegment, ProcedureSecuritySegment,
        ProcedureDeclareSegment, ProcedureSetSegment, ProcedureCallSegment,
        ProcedureWhileSegment, ProcedureBlockSegment, ProcedureExecutableSegment,
        ProcedureDefinitionSegment,
    )})
    dialect.replace(FileSegment=ProcedureFileSegment)
    config = base_config.copy() if base_config is not None else FluffConfig(
        overrides={'dialect': 'teradata', 'templater': 'raw'})
    # 4.4.0 has no public injection API for a project-local Dialect object.
    # Keep this version-pinned private hook confined to this prototype config.
    config._configs['core']['dialect_obj'] = dialect.expand()
    return config


def parse_procedure(source):
    """Parse exact LF source, returning explicit failures, never formatting SQL.

    Prototype does not use SourceMap: CR inputs are rejected until integration.
    A file is exactly one procedure with a final semicolon, not a SQL script.
    """
    if '\r' in source:
        raise ValueError('Prototype accepts LF input only')
    config = prototype_config()
    segments, violations = Lexer(config=config).lex(source)
    tree = Parser(config=config).parse(segments)
    if tree is None or tree.raw != source:
        raise ValueError('Procedure source was not preserved')
    return ProcedureParse(tree, tuple(violations))
