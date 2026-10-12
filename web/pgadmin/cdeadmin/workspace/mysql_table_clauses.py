"""Separate native SHOW CREATE foreign keys without parsing SQL expressions."""
import re

FK = re.compile(r'^\s*CONSTRAINT\s+(?:`(?P<tick>(?:``|[^`])+)`|"(?P<ansi>(?:""|[^"])+)")\s+FOREIGN\s+KEY\s*\(', re.I)


def table_layout(statement, sql_mode):
    """Separate native table-list boundaries while preserving exact clause text.

    This recognizes only lexical boundaries. It
    does not validate arbitrary SQL grammar or authorize execution of a script.
    """
    no_escape = 'NO_BACKSLASH_ESCAPES' in {part.strip().upper() for part in sql_mode.split(',')}
    ansi_quotes = 'ANSI_QUOTES' in {part.strip().upper() for part in sql_mode.split(',')}
    quote = None
    comment = None
    depth = 0
    opening = closing = start = None
    clauses = []
    i = 0
    while i < len(statement):
        char = statement[i]
        pair = statement[i:i+2]
        if comment:
            if comment == 'block' and pair == '*/':comment = None;i += 2;continue
            if comment == 'line' and char in '\r\n':comment = None
            i += 1;continue
        if quote:
            if char == '\\' and quote != '`' and not (quote == '"' and ansi_quotes) and not no_escape:
                i += 2;continue
            if char == quote:
                if i+1 < len(statement) and statement[i+1] == quote:i += 2;continue
                quote = None
            i += 1;continue
        if pair == '/*':comment = 'block';i += 2;continue
        if char == '#' or (pair == '--' and i+2 < len(statement) and statement[i+2].isspace()):
            comment = 'line';i += 1;continue
        if char in "'\"`":quote = char;i += 1;continue
        if char == '(':
            depth += 1
            if opening is None:opening = i;start = i+1
        elif char == ')':
            depth -= 1
            if depth < 0:raise ValueError('Unbalanced native table definition')
            if depth == 0 and opening is not None and closing is None:
                clauses.append(statement[start:i]);closing = i
                break
        elif char == ',' and depth == 1:
            clauses.append(statement[start:i]);start = i+1
        i += 1
    if opening is None or closing is None or quote or comment or depth:
        raise ValueError('Native table clause boundaries are unavailable')
    return {'prefix':statement[:opening], 'clauses':clauses, 'suffix':statement[closing+1:]}


def separate_foreign_keys(statement, expected, sql_mode):
    layout = table_layout(statement, sql_mode)
    remaining, foreign = [], {}
    for clause in layout['clauses']:
        match = FK.match(clause)
        if match:
            name = match.group('tick').replace('``', '`') if match.group('tick') is not None else match.group('ansi').replace('""', '"')
            if name in foreign:raise ValueError('Duplicate native foreign-key constraint')
            foreign[name] = clause.strip()
        else:remaining.append(clause)
    if set(foreign) != set(expected):
        raise ValueError('Native foreign-key definitions do not match catalog identities')
    if not remaining:raise ValueError('Native table body is empty')
    return layout['prefix'] + '(' + ','.join(remaining) + ')' + layout['suffix'], list(foreign.values())
