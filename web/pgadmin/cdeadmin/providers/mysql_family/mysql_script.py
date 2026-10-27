"""Incremental MySQL client framing using each command's observed language.

This locates command boundaries, not SQL grammar. Native compound programs
without a client delimiter retain their existing whole-command admission.
"""
import re

from ...data_studio.mysql_quoting import available, marker_at, end_of_quote


DIRECTIVE = re.compile(r'[ \t]*DELIMITER[ \t]+(\S+)[ \t]*\r?$', re.I | re.A)
WORD = re.compile(r'[A-Za-z_][A-Za-z_0-9]*')


class MySQLScriptFramingError(ValueError):
    pass


class Statements:
    def __init__(self, source):
        self.source, self.position, self.delimiter = source, 0, ';'

    def next(self, version, mode):
        source, i, start = self.source, self.position, self.position
        modes = set(mode.split(',')); meaningful = False; head = None; compound = False
        while i < len(source):
            if i == 0 or source[i - 1] == '\n':
                end = source.find('\n', i)
                if end < 0: end = len(source)
                directive = DIRECTIVE.fullmatch(source[i:end])
                if directive:
                    if meaningful: raise MySQLScriptFramingError('DELIMITER must occur between native commands')
                    delimiter = directive[1]
                    if len(delimiter) > 16 or any(char in delimiter for char in "'\"`\\"):
                        raise MySQLScriptFramingError('Unsupported MySQL client delimiter')
                    self.delimiter = delimiter
                    i = min(end + 1, len(source)); start = i
                    continue
            if source.startswith(self.delimiter, i):
                end = i; i += len(self.delimiter)
                if meaningful:
                    # The native server owns semicolons inside an undelimited
                    # routine/event/trigger. Preserve that established port.
                    if self.delimiter == ';' and compound:
                        self.position = len(source)
                        return source[start:]
                    self.position = i
                    return source[start:end]
                start = i; head = None; compound = False
                continue
            char, pair = source[i], source[i:i + 2]
            if char == '#' or pair == '--' and (i + 2 == len(source) or source[i + 2].isspace()):
                end = source.find('\n', i)
                i = len(source) if end < 0 else end
                continue
            if pair == '/*':
                # Executable comments can be the entire native command. They
                # remain byte-for-byte source, including inactive versions.
                meaningful |= source[i + 2:i + 3] == '!'
                end = source.find('*/', i + 2)
                i = len(source) if end < 0 else end + 2
                continue
            if char in "'\"`":
                meaningful = True; quote = char; i += 1
                while i < len(source):
                    if (source[i] == '\\' and quote != '`' and
                            not (quote == '"' and 'ANSI_QUOTES' in modes) and
                            'NO_BACKSLASH_ESCAPES' not in modes):
                        i += 2; continue
                    if source[i] == quote:
                        i += 1
                        if i < len(source) and source[i] == quote:
                            i += 1; continue
                        break
                    i += 1
                continue
            if char == '$' and available(version):
                marker = marker_at(source, i)
                if marker:
                    meaningful = True
                    end = end_of_quote(source, i, marker)
                    i = len(source) if end is None else end
                    continue
            if not char.isspace(): meaningful = True
            word = WORD.match(source, i)
            if word:
                value = word[0].upper(); head = head or value
                compound |= head == 'CREATE' and value in {'PROCEDURE', 'FUNCTION', 'TRIGGER', 'EVENT'}
                i = word.end()
            else: i += 1
        self.position = len(source)
        return source[start:] if meaningful else None

    def has_next(self, version, mode):
        probe = Statements(self.source)
        probe.position, probe.delimiter = self.position, self.delimiter
        try: return probe.next(version, mode) is not None
        except ValueError: return True  # Admission belongs to that command's observed language.
