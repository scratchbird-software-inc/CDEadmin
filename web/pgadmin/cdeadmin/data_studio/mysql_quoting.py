"""Lexical boundaries qualified against MySQL9.7; not a SQL/body validator."""
import re

TAG = re.compile(r'\$[A-Za-z0-9_\u0080-\U0010ffff]*\$')
IDENTIFIER = re.compile(r'[A-Za-z0-9_$\u0080-\U0010ffff]')
PARAMETER = re.compile(r'%(?:s|\(([^)]+)\)s)')


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


def parameter_spans(source, modes, *, dollar_quotes=False):
    """Locate driver bindings outside native literals, identifiers and comments."""
    i = 0; quote = None; comment = None
    while i < len(source):
        char = source[i]; pair = source[i:i + 2]
        if comment:
            if comment == 'line' and char == '\n': comment = None
            elif comment == 'block' and pair == '*/': comment = None; i += 1
        elif quote:
            if (char == '\\' and quote != '`' and not (quote == '"' and 'ANSI_QUOTES' in modes)
                    and 'NO_BACKSLASH_ESCAPES' not in modes): i += 1
            elif char == quote:
                if source[i + 1:i + 2] == quote: i += 1
                else: quote = None
        elif char == '$' and dollar_quotes:
            marker = marker_at(source, i)
            if marker:
                end = end_of_quote(source, i, marker)
                i = len(source) if end is None else end
                continue
        elif char in "'\"`": quote = char
        elif char == '#' or pair == '--' and (i + 2 == len(source) or source[i + 2].isspace()): comment = 'line'
        elif pair == '/*':
            end = source.find('*/', i + 2)
            if end < 0: return
            if dollar_quotes and source[i + 2:i + 3] == '!':
                body_start = i + 3
                directive = re.match(r'([0-9]{5,6})(?=\s|$)', source[body_start:end])
                active = directive is None or int(directive[1]) <= 90700
                if directive is not None: body_start += directive.end()
                if active:
                    for start, stop, name in parameter_spans(source[body_start:end], modes, dollar_quotes=True):
                        yield body_start + start, body_start + stop, name
            i = end + 2; continue
        elif char == '%':
            match = PARAMETER.match(source, i)
            if match:
                yield i, match.end(), match[1]
                i = match.end(); continue
        i += 1
