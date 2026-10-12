"""Bounded native reads for qualified non-character array element types."""
from ctypes import create_string_buffer

from firebird.driver import fbapi as api
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .varying_arrays import _chunked
from .array_layout import lookup, scalar_sdl, SCALAR_WIDTHS


def describe(cursor, desc):
    bounds, subtype = lookup(cursor, desc.relation, desc.field)
    dtype = bounds.array_desc_dtype
    if dtype not in SCALAR_WIDTHS:
        return None
    width = bounds.array_desc_length
    if width != SCALAR_WIDTHS[dtype]:
        raise RelationalClientError('Unexpected scalar array element width')
    return bounds, width, subtype


def rectangle(cursor, array_id, bounds, width, subtype, shape):
    count = 1
    for size in shape:
        count *= size
    data = create_string_buffer(count * width)
    received = cursor._connection._att.get_slice(
        cursor._transaction._tra, array_id, scalar_sdl(bounds), b'', data)
    if received != len(data):
        raise RelationalClientError('Incomplete scalar array slice')
    value, consumed = cursor._extract_db_array_to_list(
        width, bounds.array_desc_dtype, subtype, bounds.array_desc_scale,
        0, shape, data, 0)
    if consumed != len(data):
        raise RelationalClientError('Incomplete scalar array decoding')
    return value


def read(cursor, desc):
    layout = describe(cursor, desc)
    if layout is None:
        return False, None
    bounds, width, subtype = layout
    dimensions = [b.array_bound_upper - b.array_bound_lower + 1
                  for b in bounds.array_desc_bounds[
                      :bounds.array_desc_dimensions]]
    raw = cursor._stmt._out_buffer[desc.offset:desc.offset + desc.length]
    array_id = api.ISC_QUAD.from_buffer_copy(raw)

    return True, _chunked(bounds, dimensions, width,
                          lambda part, shape: rectangle(
                              cursor, array_id, part, width, subtype, shape))
