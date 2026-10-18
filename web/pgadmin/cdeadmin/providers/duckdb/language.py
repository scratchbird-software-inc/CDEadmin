"""DuckDB 1.5.2 parse-only SQL diagnostics and native script boundaries."""

import hashlib
import re

from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError


MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_STATEMENTS = 1000


def original_statements(source, parser):
    """Frame rewritten native statements using DuckDB's own lexical tokens.

    The native tokenizer reports UTF-8 byte offsets. Convert only the selected
    boundaries, preserving the caller's Unicode source and comments exactly.
    """
    import duckdb
    encoded=source.encode('utf8');spans=[];start=0;has_code=False
    for position,kind in duckdb.tokenize(source):
        if not 0<=position<len(encoded):raise ValueError('Native token offset is unavailable')
        if kind==duckdb.token_type.operator and encoded[position:position+1]==b';':
            if has_code:spans.append((start,position+1))
            start=position+1;has_code=False
        else:has_code=True
    if has_code:spans.append((start,len(encoded)))
    if not 1<=len(spans)<=MAX_STATEMENTS:raise ValueError('Native source exceeds the statement limit')
    positions={};previous_byte=previous_character=0
    for edge in sorted({edge for span in spans for edge in span}):
        previous_character+=len(encoded[previous_byte:edge].decode('utf8'))
        positions[edge]=previous_character;previous_byte=edge
    result=[]
    for ordinal,(first,last) in enumerate(spans,1):
        begin,end=positions[first],positions[last];text=source[begin:end]
        native=parser(text)
        if not native:raise ValueError('Native statement source is unavailable')
        result.append({'ordinal':ordinal,'source':text,'start':begin,'end':end,
            'native_type':native[0].type.name if len(native)==1 else 'MULTI',
            'native_expanded_types':[statement.type.name for statement in native]})
    return result


def analyze(source, *, script=False, parser=None, on_native_error=None):
    if not isinstance(source, str) or len(source.encode('utf8')) > MAX_SOURCE_BYTES:
        raise LanguageToolError('Source must be text no larger than 2 MiB')
    result = {
        'language_profile': 'duckdb-sql',
        'source_sha256': hashlib.sha256(source.encode('utf8')).hexdigest(),
        'authority': 'duckdb-1.5.2-native-parser',
        'parser_version': 'DuckDB 1.5.2',
        'parser_context': 'retained-native-session' if parser is not None else 'independent-native-parser',
        'grammar_valid': None, 'syntax_valid': False,
        'script_ready': False, 'statements': [], 'diagnostics': [],
        'scope': 'Native parse only; names, permissions, types and effects are checked by execution.',
    }

    def issue(code, message, offset=0):
        offset = max(0, min(len(source), offset))
        result['diagnostics'].append({'code': code, 'message': message,
            'severity': 'error', 'offset': offset,
            'line': source.count('\n', 0, offset) + 1,
            'column': offset - source.rfind('\n', 0, offset)})

    if '\x00' in source:
        issue('INVALID_SOURCE', 'SQL source contains NUL.', source.index('\x00'))
        return result
    try:
        import duckdb
    except ImportError:
        issue('PARSER_UNAVAILABLE', 'The DuckDB parser package is unavailable.')
        return result
    if duckdb.__version__ != '1.5.2':
        issue('PARSER_UNAVAILABLE', 'The installed DuckDB parser revision is not qualified.')
        return result
    try:
        selected_parser=parser if parser is not None else duckdb.extract_statements
        statements = selected_parser(source)
    except duckdb.Error as error:
        if on_native_error is not None:
            on_native_error(error)
        # Native exception strings can echo arbitrary SQL, paths and secrets.
        # Only its line number is used; never return its message to the browser.
        match = re.search(r'\bLINE\s+([1-9][0-9]*):', str(error))
        line = int(match.group(1)) if match else None
        offset = (sum(len(part) + 1 for part in source.split('\n')[:line - 1])
                  if line is not None and line <= source.count('\n') + 1 else 0)
        if isinstance(error, duckdb.ParserException):
            result['grammar_valid'] = False
            issue('DUCKDB_SYNTAX', 'Native DuckDB parser rejected the source under the current native configuration.', offset)
        else:
            issue('DUCKDB_PARSE_CONTEXT', 'Native parsing could not resolve this command in the current context.', offset)
        return result
    if not statements:
        issue('EMPTY_SOURCE', 'Source has no SQL statements.')
        return result
    if len(statements) > MAX_STATEMENTS:
        issue('SCRIPT_LIMIT', 'Script exceeds 1000 statements.')
        return result
    try:
        result['statements']=original_statements(source,selected_parser)
    except (duckdb.Error,ValueError,UnicodeError) as error:
        if isinstance(error,duckdb.Error) and on_native_error is not None:on_native_error(error)
        issue('FRAMING_UNAVAILABLE', 'Native statement boundaries could not be mapped to source.')
        result['statements'] = []
        return result
    result['grammar_valid'] = result['syntax_valid'] = True
    result['script_ready'] = bool(script)
    return result
