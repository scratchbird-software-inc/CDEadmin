"""Contain one SQLite expression without restricting native expression grammar."""
from ...sdk import RelationalClientError


def expression(value):
    if not isinstance(value, str) or not value.strip() or '\0' in value or len(value.encode()) > 65536:
        raise RelationalClientError('A bounded native SQLite expression is required')
    from ...workspace.sqlite_native_rebind import tokens
    try:
        items = tokens(value)
    except ValueError:
        raise RelationalClientError('Incomplete SQLite expression quoting or comment') from None
    if not items:
        raise RelationalClientError('A native SQLite expression is required')
    depth = 0
    for _start, _end, token in items:
        if token == '(':
            depth += 1
        elif token == ')':
            depth -= 1
            if depth < 0:
                raise RelationalClientError('SQLite expression escapes its native clause')
        elif token == ';' or token == ',' and depth == 0:
            raise RelationalClientError('One native SQLite expression is required')
    if depth:
        raise RelationalClientError('Unbalanced SQLite expression')
    # A terminating line comment cannot swallow provider-owned punctuation.
    return value.strip() + '\n'
