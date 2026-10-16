"""One opt-in grammar selection point for runtime parsing and CP01–CP05."""
from sqlfluff.core import FluffConfig
from sqlfluff.core.parser import Lexer


def is_procedure(source):
    # Token inspection only: comments/literals cannot masquerade as a header.
    # Cheap rejection only; positive selection always requires lexer tokens.
    first = source.lstrip('\ufeff \t\r\n')[:1].upper()
    if first not in ('C', 'R', '-', '/'):
        return False
    config = FluffConfig(overrides={'dialect': 'teradata', 'templater': 'raw'})
    segments, _ = Lexer(config=config).lex(source.lstrip('\ufeff'))
    code = [s.raw.upper() for s in segments if s.is_code and not s.is_meta]
    return len(code) >= 2 and code[0] in ('CREATE', 'REPLACE') and code[1] == 'PROCEDURE'


def select_config(source, config):
    if not is_procedure(source):
        return config
    from prototypes.teradata_procedures import prototype_config
    return prototype_config(config)
