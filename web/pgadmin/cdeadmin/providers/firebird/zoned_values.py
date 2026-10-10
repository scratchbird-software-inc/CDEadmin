"""Lossless native UTC plus database zone identity; no host timezone rules."""
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, time
import re

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


KINDS = {28: 'firebird-time-tz', 29: 'firebird-timestamp-tz'}


@dataclass(frozen=True)
class ZonedValue:
    code: int
    utc: object
    time_zone: str

    def envelope(self):
        text = (self.utc.isoformat(sep=' ') if self.code == 29 else
                self.utc.isoformat())
        return {'encoding': KINDS[self.code], 'utc': text,
                'time_zone': self.time_zone}


def parse(value, code=None):
    if isinstance(value, ZonedValue):
        value = value.envelope()
    if (not isinstance(value, Mapping) or
            set(value) != {'encoding', 'utc', 'time_zone'} or
            value.get('encoding') not in KINDS.values()):
        raise RelationalClientError('Invalid Firebird zoned value envelope')
    actual = next(key for key, kind in KINDS.items()
                  if kind == value['encoding'])
    if code is not None and code != actual:
        raise RelationalClientError('Firebird zoned temporal type mismatch')
    zone = value['time_zone']
    clock = r'\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?'
    pattern = clock if actual == 28 else r'\d{4}-\d{2}-\d{2}[ T]' + clock
    if (not isinstance(zone, str) or not zone or len(zone) > 63 or
            not zone.isascii() or zone.strip() != zone or
            any(ord(c) < 33 or ord(c) > 126 for c in zone) or
            not isinstance(value['utc'], str) or
            not re.fullmatch(pattern, value['utc'], re.ASCII)):
        raise RelationalClientError('Invalid Firebird UTC value or zone')
    try:
        native_class = time if actual == 28 else datetime
        utc = native_class.fromisoformat(value['utc'])
    except ValueError as exc:
        raise RelationalClientError('Invalid Firebird UTC date/time') from exc
    if utc.microsecond % 100:
        raise RelationalClientError(
            'Firebird UTC precision is 100 microseconds')
    return ZonedValue(actual, utc, zone)


def _catalog(cursor, key, value):
    # Bounded, cursor-owned cache; never share identity across databases.
    cache = getattr(cursor, '_zone_names', None)
    if cache is None:
        cache = cursor._zone_names = {}
    lookup = (key, value)
    if lookup not in cache:
        with cursor._transaction.cursor() as query:
            query.execute(
                'SELECT RDB$TIME_ZONE_ID, TRIM(RDB$TIME_ZONE_NAME) '
                'FROM RDB$TIME_ZONES WHERE ' + key + ' = ?', (value,))
            row = query.fetchone()
        if row is None:
            raise RelationalClientError('Firebird database zone unavailable')
        if len(cache) >= 512:
            cache.clear()
        cache[lookup] = row
    return cache[lookup]


def zone_name(cursor, identity):
    if 0 <= identity <= 2878:
        minutes = identity - 1439
        return ('-' if minutes < 0 else '+') + (
            f'{abs(minutes) // 60:02}:{abs(minutes) % 60:02}')
    return _catalog(cursor, 'RDB$TIME_ZONE_ID', identity)[1]


def zone_id(cursor, name):
    if re.fullmatch(r'[+-]\d{2}:\d{2}', name, re.ASCII):
        hour, minute = int(name[1:3]), int(name[4:])
        if minute > 59 or hour > 14 or hour == 14 and minute:
            raise RelationalClientError('Invalid Firebird fixed zone offset')
        return 1439 + (hour * 60 + minute) * (-1 if name[0] == '-' else 1)
    return _catalog(cursor, 'RDB$TIME_ZONE_NAME', name)[0]


def decode(cursor, raw, code):
    from firebird.driver import core, fbapi
    if code == 28:
        native = fbapi.ISC_TIME_TZ.from_buffer_copy(raw)
        utc = core._util.decode_time(native.utc_time)
    else:
        native = fbapi.ISC_TIMESTAMP_TZ.from_buffer_copy(raw)
        stamp = native.utc_timestamp
        utc = datetime.combine(core._util.decode_date(stamp.timestamp_date),
                               core._util.decode_time(stamp.timestamp_time))
    return ZonedValue(code, utc, zone_name(cursor, native.time_zone))


def encode(cursor, value, code):
    from firebird.driver import core, fbapi
    value = parse(value, code)
    native = fbapi.ISC_TIME_TZ() if code == 28 else fbapi.ISC_TIMESTAMP_TZ()
    if code == 28:
        native.utc_time = core._util.encode_time(value.utc)
    else:
        native.utc_timestamp.timestamp_date = core._util.encode_date(
            value.utc.date())
        native.utc_timestamp.timestamp_time = core._util.encode_time(
            value.utc.time())
    native.time_zone = zone_id(cursor, value.time_zone)
    return bytes(native)


def unpack(cursor, native_unpack):
    from firebird.driver.types import SQLDataType
    kinds = {SQLDataType.TIME_TZ: 28, SQLDataType.TIMESTAMP_TZ: 29}
    replacements, saved = {}, []
    buffer = cursor._stmt._out_buffer
    try:
        for index, desc in enumerate(cursor._stmt._out_desc):
            if desc.datatype not in kinds or buffer[desc.null_offset] != b'\0':
                continue
            replacements[index] = decode(cursor, buffer[
                desc.offset:desc.offset+desc.length], kinds[desc.datatype])
            saved.append(desc.null_offset)
            buffer[desc.null_offset] = b'\1'
        values = list(native_unpack())
        for index, value in replacements.items():
            values[index] = value
        return tuple(values)
    finally:
        for offset in saved:
            buffer[offset] = b'\0'


def pack(cursor, meta, buffer, parameters, native_pack):
    from ctypes import addressof, memmove
    from firebird.driver.types import SQLDataType
    kinds = {SQLDataType.TIME_TZ: 28, SQLDataType.TIMESTAMP_TZ: 29}
    delegated, replacements = list(parameters), []
    for index, value in enumerate(parameters):
        if not isinstance(value, ZonedValue):
            continue
        if index >= meta.get_count() or meta.get_type(index) not in kinds:
            raise RelationalClientError('Zoned value requires zoned parameter')
        raw = encode(cursor, value, kinds[meta.get_type(index)])
        replacements.append((index, raw))
        delegated[index] = None
    result_meta, result_buffer = native_pack(meta, buffer, delegated)
    try:
        for index, raw in replacements:
            if result_meta.get_length(index) != len(raw):
                raise RelationalClientError('Invalid native zoned width')
            memmove(addressof(result_buffer)+result_meta.get_offset(index),
                    raw, len(raw))
            result_buffer[result_meta.get_null_offset(index)] = b'\0'
    except BaseException:
        result_meta.release()
        raise
    return result_meta, result_buffer
