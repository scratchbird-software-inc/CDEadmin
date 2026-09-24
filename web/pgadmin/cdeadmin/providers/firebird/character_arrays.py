"""Character array slices sized for the attachment, not the stored charset."""
from ctypes import create_string_buffer

from firebird.driver import fbapi as api
from firebird.driver.types import DatabaseError, SQLDataType
from pgadmin.cdeadmin.sdk.relational import RelationalClientError


def read(cursor, desc):
    """Return (handled, value); leave non-character arrays to the driver."""
    connection = cursor._connection
    with cursor._transaction.cursor() as catalog:
        catalog.execute(
            'SELECT F.RDB$FIELD_TYPE, F.RDB$CHARACTER_LENGTH, '
            'F.RDB$CHARACTER_SET_ID, C.RDB$BYTES_PER_CHARACTER '
            'FROM RDB$RELATION_FIELDS R JOIN RDB$FIELDS F ON '
            'F.RDB$FIELD_NAME=R.RDB$FIELD_SOURCE '
            'LEFT JOIN RDB$CHARACTER_SETS C ON '
            'C.RDB$CHARACTER_SET_NAME=? '
            'WHERE R.RDB$RELATION_NAME=? AND R.RDB$FIELD_NAME=?',
            (connection.charset or 'NONE', desc.relation, desc.field))
        metadata = catalog.fetchone()
    if not metadata or metadata[0] not in (14, 37) or metadata[2] == 1:
        return False, None
    code, characters, _, width = metadata
    if not characters or not width:
        raise RelationalClientError('Character array charset metadata missing')
    capacity = characters * width
    if not 0 < capacity <= 65535:
        raise RelationalClientError('Character array slice width out of range')
    native = api.get_api()
    status = api.ISC_STATUS_ARRAY()
    bounds = api.ISC_ARRAY_DESC(0)
    db = connection._get_handle()
    transaction = cursor._transaction._get_handle()
    native.isc_array_lookup_bounds(
        status, db, transaction, desc.relation.encode(cursor._encoding),
        desc.field.encode(cursor._encoding), bounds)
    if api.db_api_error(status):
        raise api.exception_from_status(DatabaseError, status,
                                        'Character array bounds')
    bounds.array_desc_length = capacity
    dimensions = [bound.array_bound_upper - bound.array_bound_lower + 1
                  for bound in bounds.array_desc_bounds[
                      :bounds.array_desc_dimensions]]
    if not dimensions or any(size <= 0 for size in dimensions):
        raise RelationalClientError('Invalid character array bounds')
    count = 1
    for size in dimensions:
        count *= size
    size = capacity + (2 if code == 37 else 0)
    if count * size > 2147483647:
        raise RelationalClientError(
            'Character array exceeds native slice size')
    data = create_string_buffer(count * size)
    length = api.ISC_LONG(len(data))
    raw_id = cursor._stmt._out_buffer[desc.offset:desc.offset + desc.length]
    array_id = api.ISC_QUAD.from_buffer_copy(raw_id)
    native.isc_array_get_slice(status, db, transaction, array_id, bounds,
                               data, length)
    if api.db_api_error(status):
        raise api.exception_from_status(DatabaseError, status,
                                        'Character array read')
    leaves = []
    raw = data.raw
    for index in range(count):
        packed = raw[index * size:(index + 1) * size]
        if code == 37:
            packed = packed.split(b'\0', 1)[0]
        value = packed.decode(cursor._encoding)
        if code == 14:
            # Slice padding is byte-sized; SQL CHAR is character-sized.
            # Remove only the transport padding beyond the declared length.
            if value[characters:].strip(' '):
                raise RelationalClientError('Character array padding invalid')
            value = value[:characters]
        leaves.append(value)
    iterator = iter(leaves)

    def nest(depth):
        return [next(iterator) if depth == len(dimensions)-1 else
                nest(depth + 1) for _ in range(dimensions[depth])]

    return True, nest(0)


def unpack(cursor, native_unpack):
    """Delegate scalar decoding without changing shared driver metadata.

    The fetched row buffer belongs to this cursor. Temporarily mark only the
    handled array slots NULL so the stock decoder skips its undersized slice;
    restore every byte even if scalar/BLOB decoding raises.
    """
    buffer = cursor._stmt._out_buffer
    replacements = {}
    saved = {}
    try:
        for index, desc in enumerate(cursor._stmt._out_desc):
            if (desc.datatype != SQLDataType.ARRAY or
                    buffer[desc.null_offset] != b'\0'):
                continue
            handled, value = read(cursor, desc)
            if handled:
                replacements[index] = value
                saved[desc.null_offset] = buffer[desc.null_offset]
                buffer[desc.null_offset] = b'\1'
        result = list(native_unpack())
    finally:
        for offset, original in saved.items():
            buffer[offset] = original
    for index, value in replacements.items():
        result[index] = value
    return tuple(result)
