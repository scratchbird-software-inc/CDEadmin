"""Exact MySQL text-protocol values at the query/browser boundary."""
import base64
import binascii
import codecs
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from functools import lru_cache
import math
import re

from mysql.connector.constants import FieldType, FieldFlag, CharacterSet

from pgadmin.cdeadmin.sdk import RelationalClientError


SAFE_INTEGER = (1 << 53) - 1
INTEGER_TYPES = frozenset({
    FieldType.TINY, FieldType.SHORT, FieldType.LONG, FieldType.INT24,
    FieldType.LONGLONG, FieldType.YEAR,
})
EXACT_TEXT_TYPES = frozenset({
    FieldType.DECIMAL, FieldType.NEWDECIMAL, FieldType.FLOAT, FieldType.DOUBLE,
    FieldType.DATE, FieldType.NEWDATE, FieldType.TIME, FieldType.TIMESTAMP,
    FieldType.DATETIME,
})
BINARY_TYPES = frozenset({FieldType.GEOMETRY, FieldType.VECTOR})
CHARSETS = CharacterSet()
CHARSETS.set_mysql_version((9, 7, 0))
CODEC_NAMES = {
    'utf8mb4': 'utf8', 'utf8mb3': 'utf8', 'ucs2': 'utf_16_be',
    'utf16': 'utf_16_be', 'utf16le': 'utf_16_le', 'utf32': 'utf_32_be',
    'latin2': 'iso8859_2', 'latin5': 'iso8859_9', 'latin7': 'iso8859_13',
    'greek': 'iso8859_7', 'hebrew': 'iso8859_8', 'koi8r': 'koi8_r',
    'koi8u': 'koi8_u', 'macce': 'mac_latin2', 'macroman': 'mac_roman',
    'ujis': 'euc_jp', 'sjis': 'shift_jis',
}
LATIN1_TRANSLATION = {
    byte: ord(bytes([byte]).decode('cp1252')) for byte in range(0x80, 0xa0)
    if byte not in {0x81, 0x8d, 0x8f, 0x90, 0x9d}
}


@lru_cache(maxsize=512)
def text_codec(charset):
    try:
        name = CHARSETS.get_info(charset)[0]
    except Exception:
        return None, None
    codec = CODEC_NAMES.get(name, name)
    if name == 'latin1':
        return name, 'mysql_latin1'
    try:
        codecs.lookup(codec)
    except LookupError:
        codec = None
    return name, codec


def decode_text(raw, charset):
    name, codec = text_codec(charset)
    if codec == 'mysql_latin1':
        # MySQL maps undefined Windows-1252 positions to their C1 controls.
        return raw.decode('latin1').translate(LATIN1_TRANSLATION)
    if codec is not None:
        return raw.decode(codec)
    return dict(binary(raw), native_charset=name, charset_id=charset)


def binary(value):
    return {'encoding': 'base64',
            'data': base64.b64encode(value).decode('ascii'),
            'byte_length': len(value)}


def value(raw, column, encoding):
    if raw is None:
        return None
    raw = bytes(raw)
    kind = column[1]
    if kind in INTEGER_TYPES or kind == FieldType.BIT:
        number = (int.from_bytes(raw, 'big') if kind == FieldType.BIT
                  else int(raw))
        return number if abs(number) <= SAFE_INTEGER else str(number)
    if kind in EXACT_TEXT_TYPES:
        return raw.decode('ascii')
    if kind == FieldType.JSON:
        return raw.decode('utf-8')
    charset = column[8] if len(column) > 8 else None
    if kind in BINARY_TYPES or charset == 63:
        return binary(raw)
    if kind in {FieldType.STRING, FieldType.VAR_STRING, FieldType.VARCHAR,
                FieldType.ENUM, FieldType.SET, FieldType.BLOB,
                FieldType.TINY_BLOB, FieldType.MEDIUM_BLOB,
                FieldType.LONG_BLOB}:
        if charset is None:
            raise RelationalClientError('MySQL text result charset is absent')
        return decode_text(raw, charset)
    raise RelationalClientError('MySQL result type is not admitted')


def columns(cursor):
    descriptions = cursor.description or ()
    labels = [str(item[0]) for item in descriptions]
    bases = [name or f'column_{i + 1}' for i, name in enumerate(labels)]
    reserved, used = set(bases), set()
    result = []
    for index, item in enumerate(descriptions):
        base = bases[index]
        name, suffix = base, 2
        while name in used:
            name = f'{base}#{suffix}'
            suffix += 1
            if name in reserved:
                name = base
        used.add(name)
        kind = item[1]
        flags = item[7] if len(item) > 7 else None
        charset = item[8] if len(item) > 8 else None
        opaque_text = (kind in {
            FieldType.STRING, FieldType.VAR_STRING, FieldType.VARCHAR,
            FieldType.ENUM, FieldType.SET, FieldType.BLOB,
            FieldType.TINY_BLOB, FieldType.MEDIUM_BLOB, FieldType.LONG_BLOB,
        } and text_codec(charset)[1] is None)
        result.append({
            'name': name, 'native_name': labels[index], 'ordinal': index,
            'native_type': FieldType.get_info(kind) or str(kind),
            'native_type_code': kind, 'native_flags': flags,
            'charset_id': charset,
            'nullable': item[6] if len(item) > 6 else None,
            'unsigned': (bool(flags & FieldFlag.UNSIGNED)
                         if flags is not None else None),
            'cell_type': ('json' if opaque_text or kind in BINARY_TYPES or (
                charset == 63 and kind not in INTEGER_TYPES and
                kind not in EXACT_TEXT_TYPES and kind not in {
                    FieldType.BIT, FieldType.JSON}) else 'text'),
            'metadata_source': 'mysql-connector-python.column-definition',
        })
    return result


def parameter(item):
    if item is None or isinstance(item, (str, bool, bytes, bytearray)):
        return item
    if type(item) is int and abs(item) <= SAFE_INTEGER:
        return item
    if type(item) is float and math.isfinite(item):
        return item
    if isinstance(item, Mapping):
        encoding, data = item.get('encoding'), item.get('data')
        if (set(item) - {'encoding', 'data', 'byte_length'} or
                not isinstance(data, str)):
            raise RelationalClientError('MySQL typed parameter is invalid')
        if encoding == 'base64':
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                raise RelationalClientError(
                    'MySQL binary parameter is invalid') from None
            if 'byte_length' in item and (
                    type(item['byte_length']) is not int or
                    item['byte_length'] != len(raw)):
                raise RelationalClientError(
                    'MySQL binary parameter length does not match')
            return raw
        if set(item) != {'encoding', 'data'}:
            raise RelationalClientError('MySQL numeric parameter is invalid')
        if encoding == 'integer' and re.fullmatch(r'-?[0-9]{1,65}', data):
            return int(data)
        if encoding == 'decimal' and len(data) <= 1024:
            try:
                number = Decimal(data)
                if number.is_finite():
                    return number
            except InvalidOperation:
                pass
    raise RelationalClientError(
        'MySQL parameter requires an exact supported value or typed envelope')


def parameters(items):
    if items is None:
        return ()
    if isinstance(items, Mapping):
        if not all(isinstance(name, str) for name in items):
            raise RelationalClientError('MySQL parameter names must be text')
        return {name: parameter(item) for name, item in items.items()}
    if isinstance(items, (list, tuple)):
        return tuple(parameter(item) for item in items)
    raise RelationalClientError('MySQL parameters must be an object or array')


class Cursor:
    """Convert raw query rows independently from catalog reads."""

    def __init__(self, connection):
        self.native = connection.cursor(raw=True)
        self.encoding = connection.python_charset
        self._native_c_api = getattr(connection, '_cmysql', None)

    def execute(self, *args, **kwargs):
        if self._native_c_api is not None:
            # Connector/Python 26.7's C query path returns early for an OK
            # response before applying raw=True. A following SELECT in that
            # batch would otherwise inherit the last catalog cursor's mode.
            # This changes client conversion only; no SQL is dispatched here.
            self._native_c_api.raw(True)
        return self.native.execute(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.native, name)

    def fetchall(self):
        description = self.native.description or ()
        return [tuple(value(item, column, self.encoding)
                      for item, column in zip(row, description))
                for row in self.native.fetchall()]

    def fetchone(self):
        row = self.native.fetchone()
        if row is None:
            return None
        return tuple(value(item, column, self.encoding)
                     for item, column in zip(row, self.native.description))
