"""Lexical boundaries qualified against MySQL9.7; not a SQL/body validator."""
import re

TAG = re.compile(r'\$[A-Za-z0-9_\u0080-\U0010ffff]*\$')
IDENTIFIER = re.compile(r'[A-Za-z0-9_$\u0080-\U0010ffff]')


def available(version):
    return re.match(r'^9\.7\.0(?:[-\s]|$)', str(version)) is not None


def marker_at(source, position):
    if position and (IDENTIFIER.fullmatch(source[position - 1]) or source[position - 1] == '.'):
        return None
    match = TAG.match(source, position)
    return match[0] if match else None


def end_of_quote(source, start, marker):
    """Match the serving lexer's consumed mismatches, including dollar overlap.

    A mismatching candidate consumes its mismatched character. A dollar at
    that position therefore cannot also start another candidate delimiter.
    """
    position = start + len(marker)
    while position < len(source):
        candidate = source.find('$', position)
        if candidate < 0:
            break
        matched = 1
        while (matched < len(marker) and candidate + matched < len(source)
               and source[candidate + matched] == marker[matched]):
            matched += 1
        if matched == len(marker):
            return candidate + matched
        position = candidate + matched + 1
    return None
