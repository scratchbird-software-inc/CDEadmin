##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Lexical helpers for raw-SQL saved questions.

This is a lexer, not a SQL parser.  It exists for three narrow jobs:

* find ``{{name}}`` parameter references so they can be replaced by the
  engine's bind marker (the caller's values never enter the SQL text);
* a defence-in-depth guard that a raw question is one read-only statement;
* tokens for the SQL-to-question converter.

The guard is lexical.  It is not a sandbox: the provider connection and its
database privileges remain the authority on what a statement may do.
"""

from __future__ import annotations

import re
from collections import namedtuple

from .models import BIError

Token = namedtuple('Token', 'kind text start end')

_WORD = re.compile(r'[A-Za-z_\u0080-￿][A-Za-z0-9_$\u0080-￿]*')
_NUMBER = re.compile(r'(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?')
_PARAM = re.compile(r'\{\{\s*([A-Za-z][A-Za-z0-9_-]{0,127})\s*\}\}')
_DOLLAR = re.compile(r'\$([A-Za-z_][A-Za-z0-9_]*)?\$')
_OPERATORS = ('<>', '<=', '>=', '!=', '||', '::', '->>', '->', '==')
MAX_TOKENS = 50000

# Statements that read nothing back or change state.  A keyword counts only
# when it is not a function call (``REPLACE(...)``, ``INSERT(...)``).
_WRITE_WORDS = frozenset({
    'insert', 'update', 'delete', 'merge', 'drop', 'alter', 'create',
    'truncate', 'grant', 'revoke', 'attach', 'detach', 'pragma', 'copy',
    'call', 'exec', 'execute', 'replace', 'vacuum', 'set', 'into', 'lock',
    'install', 'load', 'export', 'import', 'checkpoint', 'reindex',
    'analyze', 'begin', 'commit', 'rollback', 'savepoint', 'use',
})


def tokenize(sql):
    """Split ``sql`` into tokens, preserving every character."""
    if not isinstance(sql, str):
        raise BIError('SQL must be text')
    tokens, index, length = [], 0, len(sql)
    while index < length:
        char = sql[index]
        if len(tokens) > MAX_TOKENS:
            raise BIError('SQL has too many tokens')
        if char.isspace():
            end = index + 1
            while end < length and sql[end].isspace():
                end += 1
            tokens.append(Token('ws', sql[index:end], index, end))
            index = end
        elif sql.startswith('--', index):
            end = sql.find('\n', index)
            end = length if end < 0 else end
            tokens.append(Token('comment', sql[index:end], index, end))
            index = end
        elif sql.startswith('/*', index):
            end = sql.find('*/', index + 2)
            if end < 0:
                raise BIError('SQL has an unterminated comment')
            end += 2
            tokens.append(Token('comment', sql[index:end], index, end))
            index = end
        elif char in '\'"`':
            end = index + 1
            while True:
                end = sql.find(char, end)
                if end < 0:
                    raise BIError('SQL has an unterminated quoted token')
                if sql.startswith(char * 2, end):
                    end += 2
                    continue
                end += 1
                break
            kind = 'string' if char == "'" else 'qident'
            tokens.append(Token(kind, sql[index:end], index, end))
            index = end
        elif sql.startswith('{{', index):
            match = _PARAM.match(sql, index)
            if match is None:
                raise BIError('malformed {{parameter}} reference')
            tokens.append(Token('param', match.group(1), index, match.end()))
            index = match.end()
        elif char == '$' and _DOLLAR.match(sql, index):
            tag = _DOLLAR.match(sql, index).group(0)
            end = sql.find(tag, index + len(tag))
            if end < 0:
                raise BIError('SQL has an unterminated dollar-quoted string')
            end += len(tag)
            tokens.append(Token('string', sql[index:end], index, end))
            index = end
        elif char.isdigit() or (char == '.' and sql[index + 1:index + 2]
                                .isdigit()):
            match = _NUMBER.match(sql, index)
            tokens.append(Token('number', match.group(0), index,
                                match.end()))
            index = match.end()
        elif _WORD.match(sql, index):
            match = _WORD.match(sql, index)
            tokens.append(Token('word', match.group(0), index, match.end()))
            index = match.end()
        else:
            for operator in _OPERATORS:
                if sql.startswith(operator, index):
                    text = operator
                    break
            else:
                text = char
            tokens.append(Token('punct', text, index, index + len(text)))
            index += len(text)
    return tokens


def significant(tokens):
    return [t for t in tokens if t.kind not in {'ws', 'comment'}]


def parameter_references(sql):
    """Return ``{{name}}`` identifiers in order of appearance."""
    return [t.text for t in tokenize(sql) if t.kind == 'param']


def bind_placeholders(sql, marker, declared):
    """Replace ``{{name}}`` tokens with ``marker``; return ``(sql, names)``.

    ``names`` lists the parameter for each marker in textual order, so the
    caller builds the positional array.  Undeclared names are rejected.  With
    the ``%s`` marker every literal ``%`` is doubled, as the driver requires
    once parameters are supplied.
    """
    tokens = tokenize(sql)
    names = [t.text for t in tokens if t.kind == 'param']
    unknown = sorted(set(names) - set(declared))
    if unknown:
        raise BIError('SQL references undeclared parameter: ' +
                      ', '.join(unknown))
    if not names:
        return sql, []
    escape = marker == '%s'
    pieces = []
    for token in tokens:
        if token.kind == 'param':
            pieces.append(marker)
        else:
            pieces.append(token.text.replace('%', '%%') if escape
                          else token.text)
    return ''.join(pieces), names


def assert_read_only_select(sql):
    """Require exactly one SELECT/WITH statement with no write keywords."""
    tokens = significant(tokenize(sql))
    while tokens and tokens[-1].text == ';' and tokens[-1].kind == 'punct':
        tokens.pop()
    if not tokens:
        raise BIError('SQL is empty')
    if any(t.kind == 'punct' and t.text == ';' for t in tokens):
        raise BIError('saved questions run a single statement')
    first = tokens[0]
    if not (first.kind == 'word' and first.text.lower() in {
            'select', 'with'}) and not (
            first.kind == 'punct' and first.text == '('):
        raise BIError('saved questions must be a SELECT statement')
    for position, token in enumerate(tokens):
        if token.kind != 'word' or token.text.lower() not in _WRITE_WORDS:
            continue
        following = tokens[position + 1] if position + 1 < len(tokens) \
            else None
        if following is not None and following.text == '(' and (
                token.text.lower() in {'replace', 'insert'}):
            continue
        raise BIError(
            f'saved questions are read-only; {token.text.upper()} is not '
            'allowed (quote the identifier if it is a column name)')
    return True
