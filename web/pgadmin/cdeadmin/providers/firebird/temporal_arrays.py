"""Scoped array buffer corrections for the qualified firebird-driver API.

ISC_DATE is signed; ISC_TIME is unsigned. The qualified driver omits signed
packing for array dates/timestamps. This cursor corrects those array leaves
without modifying driver files or global classes. Character arrays use the
lossless explicit slice adapters; fixed scalar character decoding also removes
transport expansion for legacy multibyte attachment encodings.
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
        clock = r'\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?'
        pattern = day if code == 12 else clock if code == 13 else (
            day + '[ T]' + clock)
        if not re.fullmatch(pattern, value, re.ASCII):
            raise RelationalClientError(
                'Firebird temporal array requires ISO date/time text with '
                '100-microsecond precision and no time zone')
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
    def execute(self, operation, parameters=None):
        from .materialized_budget import Budget
        self._materialized_budget = (
            (getattr(self, 'shared_materialization_budget', None) or Budget())
            if getattr(self, 'bounded_materialization', False) and
            not getattr(self, 'stream_arrays', False) else None)
        if self._materialized_budget is not None:
            self.stream_blob_threshold = -1
        return super().execute(operation, parameters)

    def _pack_input(self, meta, buffer, parameters):
        from .array_upload import pack as pack_upload
        from .zoned_values import pack as pack_zoned
        native_pack = super()._pack_input
        return pack_upload(self, meta, buffer, parameters,
                           lambda m, b, p: pack_zoned(
                               self, m, b, p, native_pack))

    def _unpack_output(self):
        from .character_arrays import unpack
        from .zoned_values import unpack as unpack_zoned
        native_unpack = super()._unpack_output
        budget = getattr(self, '_materialized_budget', None)
        if budget is not None:
            budget.before(self)
        result = unpack_zoned(self, lambda: unpack(self, native_unpack))
        return (budget.after(result, core.BlobReader) if budget is not None
                else result)

    def _validate_array_value(self, dim, dimensions, value_type, sqlsubtype,
                              value_scale, value):
        if value_type not in (fbapi.blr_sql_time_tz, fbapi.blr_timestamp_tz):
            return super()._validate_array_value(
                dim, dimensions, value_type, sqlsubtype, value_scale, value)
        from .zoned_values import parse
        if (not isinstance(value, (list, tuple)) or
                len(value) != dimensions[dim]):
            return False
        if dim == len(dimensions)-1:
            for item in value:
                parse(item, 28 if value_type == fbapi.blr_sql_time_tz else 29)
            return True
        return all(self._validate_array_value(
            dim+1, dimensions, value_type, sqlsubtype, value_scale, item)
                   for item in value)

    def _extract_db_array_to_list(self, esize, dtype, subtype, scale, dim,
                                  dimensions, buf, bufpos):
        if (dtype not in (fbapi.blr_sql_time_tz, fbapi.blr_timestamp_tz) or
                dim != len(dimensions)-1):
            return super()._extract_db_array_to_list(
                esize, dtype, subtype, scale, dim, dimensions, buf, bufpos)
        from .zoned_values import decode
        code = 28 if dtype == fbapi.blr_sql_time_tz else 29
        if esize != (8 if code == 28 else 12):
            raise RelationalClientError('Invalid zoned ARRAY width')
        values = [decode(self, buf[pos:pos+esize], code) for pos in range(
            bufpos, bufpos+esize*dimensions[dim], esize)]
        return values, bufpos+esize*dimensions[dim]

    def _fill_db_array_buffer(self, esize, dtype, subtype, scale, dim,
                              dimensions, value, valuebuf, buf, bufpos):
        if (dtype in (fbapi.blr_sql_time_tz, fbapi.blr_timestamp_tz) and
                dim == len(dimensions)-1):
            from .zoned_values import encode
            for item in value:
                raw = encode(self, item,
                             28 if dtype == fbapi.blr_sql_time_tz else 29)
                if esize != len(raw):
                    raise RelationalClientError('Invalid zoned ARRAY width')
                memmove(byref(buf, bufpos), raw, esize)
                bufpos += esize
            return bufpos
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


def cursor(connection, transaction=None):
    if not isinstance(connection, core.Connection):
        return connection.cursor()
    from .attachment_metadata import install
    install(connection)
    transaction = transaction or connection.main_transaction
    result = TemporalArrayCursor(connection, transaction)
    result.bounded_materialization = True
    # Match TransactionManager.cursor ownership exactly, so transaction
    # boundaries and attachment close clear this cursor too.
    transaction._cursors.append(weakref.ref(
        result, transaction._cursor_deleted))
    return result
