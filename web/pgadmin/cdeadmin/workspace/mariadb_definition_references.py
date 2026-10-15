"""Conservative qualified-name hints from MariaDB SHOW CREATE, not a SQL parser."""
import re

_NAME = re.compile(r'[A-Za-z_$][A-Za-z0-9_$]*')


def _tokens(source, sql_mode):
    modes = set(sql_mode.split(','))
    ansi = 'ANSI_QUOTES' in modes
    no_escape = 'NO_BACKSLASH_ESCAPES' in modes
    tokens = []
    index = 0
    while index < len(source):
        char, pair = source[index], source[index:index+2]
        if pair == '/*':
            end = source.find('*/', index+2)
            if end < 0:raise ValueError('Unterminated definition comment')
            # Executable comments may contain grammar; do not claim coverage.
            index = end+2;continue
        if char == '#' or (pair == '--' and source[index+2:index+3].isspace()):
            end = source.find('\n', index)
            index = len(source) if end < 0 else end+1;continue
        if char in "'\"`":
            quote = char
            identifier = quote == '`' or (quote == '"' and ansi)
            value = ''
            index += 1
            while index < len(source):
                char = source[index]
                if char == quote:
                    if source[index+1:index+2] == quote:
                        value += quote;index += 2;continue
                    index += 1;break
                if char == '\\' and not identifier and not no_escape:
                    index += 2;continue
                value += char;index += 1
            else:raise ValueError('Unterminated definition quote')
            tokens.append(('name' if identifier else 'literal', value));continue
        match = _NAME.match(source, index)
        if match:
            tokens.append(('word', match.group()));index += len(match.group());continue
        if not char.isspace():tokens.append(('symbol', char))
        index += 1
    return tokens


def qualified_references(source, sql_mode):
    tokens = _tokens(source, sql_mode)
    return sorted({(a[1], c[1]) for a,b,c in zip(tokens,tokens[1:],tokens[2:])
                   if a[0] in {'name', 'word'} and c[0] in {'name', 'word'} and b == ('symbol', '.')})


def relation_references(source, sql_mode, database):
    """FROM/JOIN/comma table-list hints, including nested query scopes.

    CTEs, table functions and dynamic SQL require semantic review. This scanner
    is only an ordering aid for native SHOW CREATE views.
    """
    tokens = _tokens(source, sql_mode)
    depth, contexts, references = 0, {}, set()
    for index, token in enumerate(tokens):
        if token == ('symbol', '('):depth += 1;continue
        if token == ('symbol', ')'):
            contexts.pop(depth, None);depth -= 1;continue
        if token[0] == 'word' and token[1].upper() in {'WHERE', 'GROUP', 'HAVING', 'ORDER', 'LIMIT', 'UNION', 'EXCEPT', 'INTERSECT', 'WINDOW'}:
            contexts[depth] = False;continue
        keyword = token[0] == 'word' and token[1].upper() in {'FROM', 'JOIN', 'STRAIGHT_JOIN'}
        if keyword:contexts[depth] = True
        if not keyword and not (token == ('symbol', ',') and contexts.get(depth)):
            continue
        following = tokens[index+1:index+4]
        if not following or following[0][0] not in {'name', 'word'}:continue
        if len(following) == 3 and following[1] == ('symbol', '.') and following[2][0] in {'name', 'word'}:
            references.add((following[0][1], following[2][1]))
        else:
            references.add((database, following[0][1]))
    return sorted(references)
