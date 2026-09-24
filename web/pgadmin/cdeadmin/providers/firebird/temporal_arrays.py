"""Scoped array buffer corrections for the qualified firebird-driver API.

ISC_DATE is signed; ISC_TIME is unsigned. firebird-driver 2.0.3 omits signed
packing for array dates/timestamps. This cursor corrects only those array
leaves, without modifying driver files, global classes or scalar encoding.
Character leaves use fresh, explicitly padded buffers. The legacy native
VARCHAR slice descriptor is a C string, not a length-prefixed SQL VARCHAR;
embedded NUL input must be rejected rather than silently truncated.
"""
from ctypes import byref, memmove
from datetime import date, datetime, time
import re
import weakref

from firebird.driver import core
from firebird.driver import fbapi
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def parse(value, code):
    native_class = {12: date, 13: time, 35: datetime}[code]
    if isinstance(value, str):
        day = r'\d{4}-\d{2}-\d{2}'
        clock = r'\d{2}:\d{2}:\d{2}(?:\.\d{1,4})?'
        pattern = day if code == 12 else clock if code == 13 else (
            day + '[ T]' + clock)
        if not re.fullmatch(pattern, value, re.ASCII):
            raise RelationalClientError(
                'Firebird temporal array requires ISO date/time text with '
                'at most four fractional second digits and no time zone')
        try:
            value = native_class.fromisoformat(value)
        except ValueError:
            raise RelationalClientError(
                'Invalid Firebird temporal array value')
    if type(value) is not native_class or (
            code != 12 and (value.tzinfo is not None or
                            value.microsecond % 100)):
        raise RelationalClientError(
            'Invalid Firebird temporal array type, zone or precision')
    return value


class TemporalArrayCursor(core.Cursor):
    def _unpack_output(self):
        from .character_arrays import unpack
        return unpack(self, super()._unpack_output)

    def _fill_db_array_buffer(self, esize, dtype, subtype, scale, dim,
                              dimensions, value, valuebuf, buf, bufpos):
        text_types = (fbapi.blr_text, fbapi.blr_text2)
        varying_types = (fbapi.blr_varying, fbapi.blr_varying2)
        if dtype in text_types + varying_types and dim == len(dimensions)-1:
            varying = dtype in varying_types
            capacity = esize - 2 if varying else esize
            if capacity < 1:
                raise RelationalClientError('Invalid character array size')
            for item in value:
                if not isinstance(item, str):
                    raise RelationalClientError(
                        'Character array requires text elements')
                try:
                    packed = item.encode(self._encoding)
                except UnicodeError as exc:
                    raise RelationalClientError(
                        'Character array value cannot use the connection '
                        'encoding') from exc
                if len(packed) > capacity:
                    raise RelationalClientError(
                        'Character array value exceeds native byte capacity')
                if varying and b'\0' in packed:
                    raise RelationalClientError(
                        'Native VARCHAR array slice cannot preserve '
                        'embedded NUL')
                # Never reuse ctypes .value: shorter leaves can otherwise
                # inherit bytes from the previous leaf. CHAR pads with spaces;
                # VARCHAR requires a terminating NUL and zeroed remainder.
                packed = packed.ljust(esize, b'\0' if varying else b' ')
                memmove(byref(buf, bufpos), packed, esize)
                bufpos += esize
            return bufpos
        if (dtype not in (fbapi.blr_sql_date, fbapi.blr_timestamp) or
                dim != len(dimensions)-1):
            return super()._fill_db_array_buffer(
                esize, dtype, subtype, scale, dim, dimensions, value,
                valuebuf, buf, bufpos)
        expected = 4 if dtype == fbapi.blr_sql_date else 8
        if esize != expected:
            raise RelationalClientError(
                'Unexpected native temporal array size')
        for item in value:
            item = parse(item, 12 if expected == 4 else 35)
            day = item if expected == 4 else item.date()
            packed = core._util.encode_date(day).to_bytes(
                4, 'little', signed=True)
            if expected == 8:
                packed += core._util.encode_time(item.time()).to_bytes(
                    4, 'little', signed=False)
            memmove(byref(buf, bufpos), packed, esize)
            bufpos += esize
        return bufpos


def cursor(connection):
    if not isinstance(connection, core.Connection):
        return connection.cursor()
    transaction = connection.main_transaction
    result = TemporalArrayCursor(connection, transaction)
    # Match TransactionManager.cursor ownership exactly, so transaction
    # boundaries and attachment close clear this cursor too.
    transaction._cursors.append(weakref.ref(
        result, transaction._cursor_deleted))
    return result
