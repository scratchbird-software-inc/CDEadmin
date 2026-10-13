"""DuckDB 1.5.2 parse-only SQL diagnostics and native script boundaries."""

import hashlib
import re

from pgadmin.cdeadmin.data_studio.language_tools import LanguageToolError


MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_STATEMENTS = 1000


def analyze(source, *, script=False):
    if not isinstance(source, str) or len(source.encode('utf8')) > MAX_SOURCE_BYTES:
        raise LanguageToolError('Source must be text no larger than 2 MiB')
    result = {
        'language_profile': 'duckdb-sql',
        'source_sha256': hashlib.sha256(source.encode('utf8')).hexdigest(),
        'authority': 'duckdb-1.5.2-native-parser',
        'parser_version': 'DuckDB 1.5.2',
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
        statements = duckdb.extract_statements(source)
    except duckdb.Error as error:
        # Native exception strings can echo arbitrary SQL, paths and secrets.
        # Only its line number is used; never return its message to the browser.
        match = re.search(r'\bLINE\s+([1-9][0-9]*):', str(error))
        line = int(match.group(1)) if match else None
        offset = (sum(len(part) + 1 for part in source.split('\n')[:line - 1])
                  if line is not None and line <= source.count('\n') + 1 else 0)
        result['grammar_valid'] = False
        issue('DUCKDB_SYNTAX', 'Native DuckDB parser rejected the source.', offset)
        return result
    if not statements:
        issue('EMPTY_SOURCE', 'Source has no SQL statements.')
        return result
    if len(statements) > MAX_STATEMENTS:
        issue('SCRIPT_LIMIT', 'Script exceeds 1000 statements.')
        return result
    position = 0
    for ordinal, statement in enumerate(statements, 1):
        text = statement.query
        start = source.find(text, position)
        if not text or start < 0:
            issue('FRAMING_UNAVAILABLE', 'Native statement boundaries could not be mapped to source.', position)
            result['statements'] = []
            return result
        end = start + len(text)
        result['statements'].append({'ordinal': ordinal, 'source': text,
            'start': start, 'end': end, 'native_type': statement.type.name})
        position = end
    result['grammar_valid'] = result['syntax_valid'] = True
    result['script_ready'] = bool(script)
    return result
