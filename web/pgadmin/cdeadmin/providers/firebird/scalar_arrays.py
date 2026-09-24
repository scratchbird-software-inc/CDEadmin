"""Bounded native reads for qualified non-character array element types."""
from ctypes import create_string_buffer

from firebird.driver import fbapi as api
from firebird.driver.types import DatabaseError
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .varying_arrays import _chunked


def read(cursor, desc):
    native = api.get_api()
    status = api.ISC_STATUS_ARRAY()
    bounds = api.ISC_ARRAY_DESC(0)
    db = cursor._connection._get_handle()
    transaction = cursor._transaction._get_handle()
    native.isc_array_lookup_bounds(
        status, db, transaction, desc.relation.encode(cursor._encoding),
        desc.field.encode(cursor._encoding), bounds)
    if api.db_api_error(status):
        raise api.exception_from_status(DatabaseError, status,
                                        'Scalar array bounds')
    dtype = bounds.array_desc_dtype
    sizes = {api.blr_short: 2, api.blr_long: 4, api.blr_int64: 8,
             api.blr_int128: 16, api.blr_float: 4, api.blr_double: 8,
             api.blr_bool: 1, api.blr_dec64: 8, api.blr_dec128: 16,
             api.blr_sql_date: 4, api.blr_sql_time: 4, api.blr_timestamp: 8}
    if dtype not in sizes:
        return False, None
    width = bounds.array_desc_length
    if width != sizes[dtype]:
        raise RelationalClientError('Unexpected scalar array element width')
    with cursor._transaction.cursor() as catalog:
        catalog.execute(
            'SELECT F.RDB$FIELD_SUB_TYPE FROM RDB$RELATION_FIELDS R '
            'JOIN RDB$FIELDS F ON F.RDB$FIELD_NAME=R.RDB$FIELD_SOURCE '
            'WHERE R.RDB$RELATION_NAME=? AND R.RDB$FIELD_NAME=?',
            (desc.relation, desc.field))
        row = catalog.fetchone()
    if row is None:
        raise RelationalClientError('Scalar array subtype unavailable')
    subtype = row[0] or 0
    dimensions = [b.array_bound_upper - b.array_bound_lower + 1
                  for b in bounds.array_desc_bounds[
                      :bounds.array_desc_dimensions]]
    raw = cursor._stmt._out_buffer[desc.offset:desc.offset + desc.length]
    array_id = api.ISC_QUAD.from_buffer_copy(raw)

    def rectangle(part, shape):
        count = 1
        for size in shape:
            count *= size
        data = create_string_buffer(count * width)
        length = api.ISC_LONG(len(data))
        slice_status = api.ISC_STATUS_ARRAY()
        native.isc_array_get_slice(slice_status, db, transaction, array_id,
                                   part, data, length)
        if api.db_api_error(slice_status):
            raise api.exception_from_status(DatabaseError, slice_status,
                                            'Scalar array read')
        if length.value != len(data):
            raise RelationalClientError('Incomplete scalar array slice')
        value, consumed = cursor._extract_db_array_to_list(
            width, dtype, subtype, part.array_desc_scale, 0, shape, data, 0)
        if consumed != len(data):
            raise RelationalClientError('Incomplete scalar array decoding')
        return value

    return True, _chunked(bounds, dimensions, width, rectangle)
