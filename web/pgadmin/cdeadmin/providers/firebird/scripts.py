"""Firebird SQL script preflight; no native calls or host commands.

Lexical authority: Firebird 5.0.4 src/isql/isql.epp get_statement/frontend,
MAXTERM_SIZE in isql.h, and the native DSQL non-nested comment rules.
"""
from dataclasses import dataclass
import hashlib
import re

from ...sdk.relational import RelationalClientError

MAX_SOURCE_BYTES = 1024 * 1024
MAX_ENTRIES = 1000
SPACE = ' \t\r\n\f'


@dataclass(frozen=True)
class Entry:
    kind: str
    source: str
    line: int
    offset: int
    value: object = None


class ScriptPreflightError(RelationalClientError):
    """Safe, source-free script validation diagnostic."""


def _error(line, detail):
    # Never echo SQL, credentials, paths or literals into diagnostics.
    return ScriptPreflightError(f'Firebird script line {line}: {detail}')


def _quote_end(source, start, line):
    quote = source[start]
    if quote == "'" and start and source[start-1] in 'qQ':
        if start + 1 >= len(source):
            raise _error(line, 'unterminated alternate-quoted string')
        opening = source[start+1]
        pairs = {'{': '}', '[': ']', '(': ')', '<': '>'}
        closing = pairs.get(opening, opening)
        end = source.find(closing + "'", start+2)
        if end < 0:
            raise _error(line, 'unterminated alternate-quoted string')
        return end + 2
    index = start + 1
    while index < len(source):
        if source[index] == quote:
            if index + 1 < len(source) and source[index+1] == quote:
                index += 2
                continue
            return index + 1
        index += 1
    raise _error(line, 'unterminated quoted string or identifier')


def _without_comments(source):
    parts, index = [], 0
    while index < len(source):
        if source.startswith('--', index):
            end = source.find('\n', index+2)
            index = len(source) if end < 0 else end
            parts.append(' ')
        elif source.startswith('/*', index):
            index = source.index('*/', index+2) + 2
            parts.append(' ')
        elif source[index] in "'\"":
            end = _quote_end(source, index, 1)
            parts.append(source[index:end])
            index = end
        else:
            parts.append(source[index])
            index += 1
    return ''.join(parts).strip(SPACE)


def _classify(source, line, offset):
    text = _without_comments(source)
    if not text:
        return None
    words = re.split(r'[ \t\r\n\f]+', text)
    upper = [word.upper() for word in words]
    if len(words) >= 2 and upper[0] == 'SET':
        option = upper[1]
        if len(option) >= 4 and 'TERMINATOR'.startswith(option):
            if len(words) not in (2, 3):
                raise _error(line, 'SET TERM requires one new delimiter')
            term = words[2] if len(words) == 3 else ';'
            if (not term.isascii() or not 1 <= len(term) <= 31 or
                    any(c.isspace() or c in "'\"-/*" for c in term)):
                raise _error(line, 'invalid script delimiter')
            return Entry('terminator', source, line, offset, term)
        if upper[1:3] == ['SQL', 'DIALECT']:
            if len(words) != 4 or words[3] not in ('1', '2', '3'):
                raise _error(line, 'SET SQL DIALECT requires 1, 2 or 3')
            return Entry('dialect', source, line, offset, int(words[3]))
        if option == 'BAIL' or (
                len(option) >= 4 and 'AUTODDL'.startswith(option)):
            if len(words) != 3 or upper[2] not in ('ON', 'OFF'):
                raise _error(line, 'script setting requires explicit ON/OFF')
            return Entry('bail' if option == 'BAIL' else 'autoddl',
                         source, line, offset, upper[2] == 'ON')
        client_options = ('STATS', 'COUNT', 'LIST', 'PLAN', 'PLANONLY',
                          'EXPLAIN', 'BLOBDISPLAY', 'ECHO', 'WIDTH', 'NAMES',
                          'SQLDA_DISPLAY', 'EXEC_PATH_DISPLAY', 'SQL',
                          'WARNINGS', 'WNG', 'HEADING', 'BULK_INSERT',
                          'ROWCOUNT', 'MAXROWS', 'LOCAL_TIMEOUT',
                          'KEEP_TRAN_PARAMS', 'PER_TABLE_STATS', 'WIRE_STATS')
        client_prefixes = (('STATS', 4), ('BLOBDISPLAY', 4),
                           ('WARNINGS', 7), ('KEEP_TRAN_PARAMS', 9),
                           ('PER_TABLE_STATS', 7), ('WIRE_STATS', 4))
        if (option in client_options or any(
                len(option) >= minimum and name.startswith(option)
                for name, minimum in client_prefixes) or
                (option == 'TIME' and upper[2:3] != ['ZONE'])):
            raise _error(line, 'client setting requires its workspace control')
    client_commands = {'SHOW', 'ADD', 'COPY', 'BLOBVIEW', 'BLOBDUMP', 'SHELL',
                       'CONNECT', 'EDIT', 'QUIT', 'EXIT', '?', 'HELP',
                       'PASSTHROUGH'}
    command = upper[0]
    if (command in client_commands or upper == ['SET'] or
            (len(command) >= 3 and 'OUTPUT'.startswith(command)) or
            (len(command) >= 2 and 'INPUT'.startswith(command)) or
            upper[:2] in (['CREATE', 'DATABASE'], ['DROP', 'DATABASE'])):
        raise _error(line, 'client command requires its workspace workflow')
    return Entry('sql', source, line, offset)


def parse(source):
    if (not isinstance(source, str) or '\0' in source or
            len(source) > MAX_SOURCE_BYTES):
        raise _error(1, 'source must be text without NUL, at most 1 MiB UTF-8')
    try:
        encoded_size = len(source.encode('utf8'))
    except UnicodeEncodeError:
        raise _error(1, 'source must be valid UTF-8 text') from None
    if encoded_size > MAX_SOURCE_BYTES:
        raise _error(1, 'source exceeds 1 MiB UTF-8')
    entries, delimiter = [], ';'
    index = start = 0
    line = first_line = 1
    valuable = False
    while index < len(source):
        if source.startswith('--', index):
            end = source.find('\n', index+2)
            index = len(source) if end < 0 else end
            continue
        if source.startswith('/*', index):
            end = source.find('*/', index+2)
            if end < 0:
                raise _error(line, 'unterminated block comment')
            line += source.count('\n', index, end+2)
            index = end+2
            continue
        if source.startswith(delimiter, index):
            entry = _classify(source[start:index], first_line, start)
            old_length = len(delimiter)
            if entry is not None:
                entries.append(entry)
                if len(entries) > MAX_ENTRIES:
                    raise _error(first_line, 'script exceeds 1000 entries')
                if entry.kind == 'terminator':
                    delimiter = entry.value
            index += old_length
            start = index
            valuable = False
            first_line = line
            continue
        if not valuable and source[index] not in SPACE:
            valuable = True
            first_line = line
        if source[index] in "'\"":
            end = _quote_end(source, index, line)
            line += source.count('\n', index, end)
            index = end
        else:
            if source[index] == '\n':
                line += 1
            index += 1
    if valuable:
        raise _error(first_line, 'final statement is missing its delimiter')
    if not entries:
        raise _error(1, 'script contains no statements or directives')
    return tuple(entries)


def preview(source):
    from .transaction_sql import starts_transaction, transaction_command
    entries = parse(source)

    def action(entry):
        command = transaction_command(entry.source)
        if command:
            return command[0] + (' retaining' if command[1] else '')
        return 'set transaction' if starts_transaction(entry.source) else None

    return {
        'source_sha256': hashlib.sha256(source.encode('utf8')).hexdigest(),
        'total_entries': len(entries),
        'entries': [{'index': index, 'line': entry.line,
                     'offset': entry.offset, 'kind': entry.kind,
                     'value': entry.value, 'transaction_action': action(entry)}
                    for index, entry in enumerate(entries, 1)],
        'native_work_requested': False,
        'default_autoddl': False,
        'default_bail': True,
    }
