"""Project-local colon bind tokens; no masking, templating or text substitution."""
from sqlfluff.core.parser import CodeSegment, Ref, RegexLexer, Sequence, TypedParser


def add_named_parameters(dialect):
    from formatter_modules.teradata_unicode import add_unicode_identifiers
    add_unicode_identifiers(dialect)
    # Runs after quote/comment/casting lexers, before the bare colon fallback.
    # A bind is one indivisible token; CP02 cannot treat its name as an identifier.
    dialect.insert_lexer_matchers([
        RegexLexer('named_parameter', r':[A-Za-z_][A-Za-z0-9_]*', CodeSegment),
    ], before='colon')
    dialect.add(NamedBindParameterSegment=TypedParser(
        'named_parameter', CodeSegment, type='named_parameter'))
    # Preserve typed-literal syntax: `DATE '...'` is valid, `id:Bind` is not.
    # ANSI's SELECT-element typed literal uses LiteralGrammar, unlike its
    # expression grammar. Keep that one branch on the original literal set.
    dialect.add(UnboundLiteralGrammar=dialect.get_grammar('LiteralGrammar').copy())
    dialect.replace(BaseExpressionElementGrammar=dialect.get_grammar(
        'BaseExpressionElementGrammar').copy(
            remove=[Sequence(Ref('DatatypeSegment'), Ref('LiteralGrammar'))],
            insert=[Sequence(Ref('DatatypeSegment'), Ref('UnboundLiteralGrammar'))]))
    dialect.replace(LiteralGrammar=dialect.get_grammar('LiteralGrammar').copy(
        insert=[Ref('NamedBindParameterSegment')]))
    return dialect


def parameter_config(config):
    from sqlfluff.core.dialects import load_raw_dialect
    import sqlfluff
    if sqlfluff.__version__ != '4.4.0':
        raise RuntimeError('Named parameter grammar requires SQLFluff 4.4.0')
    dialect = add_named_parameters(load_raw_dialect('teradata').copy_as('teradata_parameters'))
    result = config.copy()
    # Same pinned object-injection API as the procedural dialect; no registry edits.
    result._configs['core']['dialect_obj'] = dialect.expand()
    return result
