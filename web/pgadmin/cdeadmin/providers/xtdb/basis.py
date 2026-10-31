"""Database names from an XTDB 2.1.0 snapshot token.

Checked on 2.1.0 (source and live): pg_catalog.pg_database returns only the
connected database, and information_schema.tables reports one catalog, so
no query lists the attached databases. SHOW SNAPSHOT_TOKEN does: the token
is the base64 of a TimeBasis protobuf keyed by every attached database
(api/src/main/proto/xtdb/proto/basis.proto, ``map<string, SystemTimes>
databases = 1``; written by xtdb.basis/->time-basis-str). Owner direction
2026-10-31: offer only what can be read back, by any engine method.
"""
import base64
import binascii

SUPPORTED_VERSION = '2.1.0'
_LENGTH_DELIMITED = 2
_VARINT = 0
_FIXED64 = 1
_FIXED32 = 5


class Unread(Exception):
    """The snapshot token could not be decoded."""


def _varint(data, index):
    value = shift = 0
    while True:
        if index >= len(data) or shift > 63:
            raise Unread('snapshot token ends inside a number')
        byte = data[index]
        index += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, index


def _fields(data):
    index = 0
    while index < len(data):
        key, index = _varint(data, index)
        number, wire = key >> 3, key & 7
        if wire == _LENGTH_DELIMITED:
            length, index = _varint(data, index)
            if index + length > len(data):
                raise Unread('snapshot token field is truncated')
            yield number, data[index:index + length]
            index += length
        elif wire == _VARINT:
            _, index = _varint(data, index)
        elif wire in (_FIXED64, _FIXED32):
            index += 8 if wire == _FIXED64 else 4
        else:
            raise Unread(f'snapshot token has wire type {wire}')


def database_names(token):
    """The database names a snapshot token is keyed by, sorted."""
    if not token:
        raise Unread('the server returned no snapshot token')
    try:
        data = base64.b64decode(token, validate=True)
    except (binascii.Error, ValueError):
        raise Unread('snapshot token is not base64') from None
    names = set()
    for number, entry in _fields(data):
        if number != 1:
            continue
        key = [value for field, value in _fields(entry) if field == 1]
        if len(key) != 1:
            raise Unread('snapshot token entry has no database name')
        try:
            names.add(key[0].decode('utf-8'))
        except UnicodeDecodeError:
            raise Unread('snapshot token database name is not UTF-8') \
                from None
    if not names:
        raise Unread('snapshot token names no database')
    return sorted(names)
