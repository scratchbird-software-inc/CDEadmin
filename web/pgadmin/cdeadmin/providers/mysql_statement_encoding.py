"""Exact native statement bytes; control queries and results remain UTF-8."""
from contextlib import contextmanager
import re


@contextmanager
def statement_context(connection, cursor, source, context):
    charset, collation = context['character_set_client'], context['collation_connection']
    if not all(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_]+', value)
               for value in (charset, collation)):
        raise ValueError('Invalid native charset/collation identity')
    if not isinstance(source, str) or '\x00' in source or len(source.encode('utf8')) > 1024 * 1024:
        raise ValueError('Native statement requires bounded text without NUL')
    connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
    try:
        if charset in {'utf8mb4', 'utf8mb3', 'utf8'}:
            if charset != 'utf8mb4' and any(ord(char) > 0xffff for char in source):
                raise ValueError('Native UTF-8 client context cannot represent supplementary characters')
            encoded = source  # The owned connector encodes UTF-8 exactly.
        else:
            cursor.execute('SELECT CAST(CONVERT(%s USING ' + charset + ') AS BINARY), '
                           'CONVERT(CONVERT(%s USING ' + charset + ') USING utf8mb4)', (source, source))
            encoded, roundtrip = cursor.fetchone()
            if not isinstance(encoded, (bytes, bytearray)) or roundtrip != source:
                raise ValueError('Native character conversion would lose statement text')
            encoded = bytes(encoded)
            if len(encoded) > 1024 * 1024:
                raise ValueError('Native statement bytes exceed 1 MiB')
        cursor.execute('SET SESSION character_set_client=%s', (charset,))
        cursor.execute('SET SESSION collation_connection=%s', (collation,))
        yield encoded
    finally:
        connection.set_charset_collation(charset='utf8mb4', collation='utf8mb4_0900_ai_ci')
