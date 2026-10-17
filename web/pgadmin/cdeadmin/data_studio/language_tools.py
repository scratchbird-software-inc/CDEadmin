"""Side-effect-free native lexical diagnostics and bounded script framing.

Lexical acceptance is deliberately not advertised as full SQL grammar acceptance.
Native parse-only validators can add stronger evidence through the provider port.
"""
import hashlib
import json
import re
import sqlite3

SQL = frozenset({'firebird-sql', 'mysql-sql', 'mariadb-sql', 'postgresql-sql',
                 'sqlite-sql', 'duckdb-sql', 'cockroachdb-sql', 'ysql', 'tidb-sql', 'vitess-sql',
                 'dolt-sql', 'xtdb-sql-2.1', 'immudb-sql', 'clickhouse-sql', 'influxdb3-sql',
                 'influxdb3-influxql', 'opensearch-sql', 'opensearch-ppl', 'cql-3', 'ycql', 'cypher'})
MYSQL = frozenset({'mysql-sql', 'mariadb-sql',
                  'tidb-sql', 'vitess-sql', 'dolt-sql'})
DOLLAR = frozenset({'postgresql-sql', 'cockroachdb-sql',
                   'ysql', 'duckdb-sql', 'xtdb-sql-2.1'})
JSON_LANGUAGES = frozenset({'foundationdb-keyvalue-json', 'tikv-keyvalue-json',
                            'mongodb-query-api-json', 'milvus-query-search-api', 'opensearch-query-dsl',
                            'ignite-sql-keyvalue'})
COMBINED = frozenset({'opensearch-sql-ppl', 'influxdb3-sql-influxql'})


class LanguageToolError(ValueError):
    pass


def capabilities(language):
    return {'language_profile': language,
            'validation_authority': 'json-syntax' if language in JSON_LANGUAGES else 'native-lexical' if language in SQL else 'unavailable',
            'full_grammar_validation': False,
            'script_framing': language in SQL and language not in {'firebird-sql', 'influxdb3-influxql', 'opensearch-ppl', 'cypher'},
            'script_policy': 'stop-on-error-or-unknown; no automatic replay',
            'client_commands': ['DELIMITER'] if language in MYSQL else []}


def analyze(source, language, *, script=False, settings=None):
    if not isinstance(source, str) or len(source.encode()) > 2 * 1024 * 1024:
        raise LanguageToolError('Source must be text no larger than 2 MiB')
    settings = dict(settings or {})
    diagnostics = []
    statements = []

    def issue(code, message, at=0):
        diagnostics.append({'code': code, 'message': message, 'severity': 'error',
                            'offset': at, 'line': source.count('\n', 0, at) + 1,
                            'column': at - (source.rfind('\n', 0, at) + 1) + 1})
    digest = hashlib.sha256(source.encode()).hexdigest()
    result = {'language_profile': language, 'source_sha256': digest, 'diagnostics': diagnostics,
              'statements': statements, 'authority': capabilities(language)['validation_authority'],
              'grammar_valid': None, 'script_ready': False}
    if language in COMBINED:
        issue('LANGUAGE_SELECTION_REQUIRED',
              'Select one exact language, not a combined profile.')
        return result
    if language in JSON_LANGUAGES:
        try:
            json.loads(source)
        except json.JSONDecodeError as exc:
            issue('JSON_SYNTAX', exc.msg, exc.pos)
        result['syntax_valid'] = not diagnostics
        result['scope'] = 'JSON syntax only; native API/operator schemas remain provider-owned.'
        return result
    if language not in SQL:
        result['scope'] = 'No local validator is registered for this language.'
        return result
    quote = None
    quote_start = 0
    block = 0
    line_comment = False
    dollar = None
    stack = []
    start = 0
    i = 0
    delimiter = ';'
    clean = list(source)

    def append(end):
        text = source[start:end].strip()
        meaningful = ''.join(clean[start:end]).strip()
        if text and meaningful:
            statements.append({'ordinal': len(statements) + 1,
                              'source': text, 'start': start, 'end': end})
    while i < len(source):
        c = source[i]
        pair = source[i:i + 2]
        if line_comment:
            clean[i] = ' '
            if c == '\n':
                line_comment = False
            i += 1
            continue
        if block:
            clean[i] = ' '
            if pair == '/*' and language in DOLLAR:
                block += 1
                clean[i:i + 2] = [' ', ' ']
                i += 2
            elif pair == '*/':
                block -= 1
                clean[i:i + 2] = [' ', ' ']
                i += 2
            else:
                i += 1
            continue
        if dollar:
            if source.startswith(dollar, i):
                clean[i:i + len(dollar)] = [' '] * len(dollar)
                i += len(dollar)
                dollar = None
            else:
                clean[i] = ' '
                i += 1
            continue
        if quote:
            clean[i] = ' '
            mysql_string = quote != '`' and not (
                quote == '"' and settings.get('ansi_quotes') is True)
            if c == '\\' and language in MYSQL and mysql_string and settings.get(
                    'no_backslash_escapes') is not True:
                if settings.get('no_backslash_escapes') is None:
                    issue(
                        'SESSION_MODE_REQUIRED',
                        'Backslash quoting requires the observed NO_BACKSLASH_ESCAPES setting.',
                        i)
                if quote == '"' and settings.get('ansi_quotes') is None:
                    issue('SESSION_MODE_REQUIRED',
                          'Double-quote framing requires the observed ANSI_QUOTES setting.', i)
                if i + 1 < len(source):
                    clean[i + 1] = ' '
                i += 2
                continue
            if c == '\\' and language in DOLLAR:
                issue(
                    'SESSION_MODE_REQUIRED',
                    'Backslash strings require native session-aware framing.',
                    i)
            if c == quote:
                if i + 1 < len(source) and source[i + 1] == quote:
                    clean[i + 1] = ' '
                    i += 2
                    continue
                quote = None
            i += 1
            continue
        if script and (i == 0 or source[i - 1] == '\n'):
            line = source[i:source.find(
                '\n', i) if '\n' in source[i:] else len(source)]
            directive = re.fullmatch(r'\s*DELIMITER\s+(\S+)\s*', line, re.I)
            if directive and language in MYSQL:
                if ''.join(clean[start:i]).strip():
                    issue(
                        'DELIMITER_BOUNDARY',
                        'DELIMITER must occur between statements.',
                        i)
                delimiter = directive.group(1)
                if len(delimiter) > 16 or any(
                        x in delimiter for x in "'\"`\\"):
                    issue('DELIMITER_INVALID', 'Unsupported delimiter.', i)
                clean[i:i + len(line)] = [' '] * len(line)
                i += len(line)
                start = i
                continue
            if re.match(
                    r'\s*(?:\\|\.|SOURCE\s|SYSTEM\s|CONNECT\s)', line, re.I):
                issue(
                    'CLIENT_COMMAND_UNSUPPORTED',
                    'Client command is not admitted by this script adapter.',
                    i)
        mysql_comment = language not in MYSQL or i + \
            2 >= len(source) or source[i + 2].isspace()
        if pair == '--' and mysql_comment or (c == '#' and language in MYSQL):
            clean[i] = ' '
            line_comment = True
            i += 1
            continue
        if pair == '/*' and language in MYSQL and source[i:i + 3] == '/*!':
            issue(
                'EXECUTABLE_COMMENT_UNSUPPORTED',
                'Executable comments require native client framing.',
                i)
        if pair == '/*':
            block = 1
            quote_start = i
            clean[i:i + 2] = [' ', ' ']
            i += 2
            continue
        if c in "'\"`":
            if c == '`' and language not in MYSQL | {
                    'sqlite-sql', 'clickhouse-sql', 'cypher'}:
                issue(
                    'QUOTE_DIALECT',
                    'Backtick identifiers are not admitted for this language.',
                    i)
            quote = c
            quote_start = i
            clean[i] = ' '
            i += 1
            continue
        if c == '$' and language in DOLLAR:
            match = re.match(r'\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$', source[i:])
            if match:
                dollar = match.group()
                quote_start = i
                clean[i:i + len(dollar)] = [' '] * len(dollar)
                i += len(dollar)
                continue
        if c in '([':
            stack.append((c, i))
        elif c in ')]':
            if not stack or (stack[-1][0], c) not in {('(', ')'), ('[', ']')}:
                issue('UNBALANCED', 'Unmatched closing delimiter.', i)
            else:
                stack.pop()
        if not stack and source.startswith(delimiter, i):
            segment = ''.join(clean[start:i]).strip()
            if language in {'cql-3', 'ycql'} and re.match(r'BEGIN\s+(?:(?:UNLOGGED|COUNTER)\s+)?BATCH\b',
                                                          segment, re.I) and not re.search(r'APPLY\s+BATCH\s*$', segment, re.I):
                i += len(delimiter)
                continue
            if language == 'sqlite-sql' and re.match(r'CREATE\s+(?:TEMP(?:ORARY)?\s+)?TRIGGER\b',
                                                     segment, re.I) and not sqlite3.complete_statement(source[start:i + 1]):
                i += 1
                continue
            if script and delimiter == ';' and re.match(
                    r'CREATE\s+(?:OR\s+REPLACE\s+)?(?:PROCEDURE|FUNCTION|TRIGGER|PACKAGE)\b', segment, re.I) and language in MYSQL:
                issue(
                    'BODY_DELIMITER_REQUIRED',
                    'Use an explicit DELIMITER for stored program bodies.',
                    start)
            append(i)
            i += len(delimiter)
            start = i
            continue
        i += 1
    if quote or dollar or block:
        issue(
            'UNTERMINATED',
            'Unterminated quoted text or comment.',
            quote_start)
    for _, at in stack:
        issue('UNBALANCED', 'Unclosed delimiter.', at)
    append(len(source))
    if len(statements) > 1000:
        issue('SCRIPT_LIMIT', 'Script exceeds 1000 statements.')
    if not source.strip():
        issue('EMPTY_SOURCE', 'Source is empty.')
    if script and language in {
            'influxdb3-influxql', 'opensearch-ppl', 'cypher'}:
        issue(
            'NATIVE_FRAMING_REQUIRED',
            'This language requires a dedicated script framing adapter.')
    if script and re.search(
            r'\bSET\s+(?:(?:SESSION|LOCAL)\s+)?(?:SQL_MODE|STANDARD_CONFORMING_STRINGS)\b|\bBEGIN\s+ATOMIC\b', ''.join(clean), re.I):
        issue(
            'SESSION_FRAMING_CHANGE',
            'Session syntax changes and unquoted routine bodies require native client framing.')
    if script and language == 'firebird-sql':
        issue('FIREBIRD_ADAPTER', 'Use the dedicated Firebird script tool.')
    if script and re.search(
            r'\bCOPY\b[\s\S]*\bFROM\s+STDIN\b|\bINSERT\b[\s\S]*\bFORMAT\b', ''.join(clean), re.I):
        issue(
            'DATA_FRAMING_REQUIRED',
            'Use the native import tool for embedded data payloads.')
    result.update(syntax_valid=not diagnostics, script_ready=script and bool(statements) and not diagnostics,
                  scope='Lexical structure and statement boundaries only; native grammar/semantics are not certified.')
    return result
