"""Character array slices sized for the attachment, not the stored charset."""
from ctypes import addressof, create_string_buffer, memmove

from firebird.driver import fbapi as api
from firebird.driver.types import SQLDataType
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .varying_arrays import TEXT_CHARSETS
from .array_layout import lookup
from .array_sdl import transport_charset


def metadata(cursor, relation, field):
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
            (connection.charset or 'NONE', relation, field))
        result = catalog.fetchone()
    if result and result[0] in (14, 37) and result[2] == 1:
        return (*result[:3], 1)
    if result and connection.charset == 'UNICODE_FSS':
        return (*result[:3], 4)
    return (result if result and result[0] in (14, 37) and result[2] != 1
            else None)


def layout(cursor, relation, field, description):
    code, characters, _, width = description
    if not characters or not width:
        raise RelationalClientError('Character array charset metadata missing')
    capacity = characters * width
    if capacity <= 0 or capacity + (2 if code == 37 else 0) > 65535:
        raise RelationalClientError('Character array slice width out of range')
    bounds, _ = lookup(cursor, relation, field)
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
    if count * bounds.stored_element_width > 2147483647:
        raise RelationalClientError(
            'Character array exceeds native slice size')
    return bounds, dimensions, size, count


def read(cursor, desc):
    """Return (handled, value) for bounded character or scalar array reads."""
    description = metadata(cursor, desc.relation, desc.field)
    if description is None:
        from .scalar_arrays import read as read_scalar
        return read_scalar(cursor, desc)
    code, characters, charset, _ = description
    bounds, dimensions, _, _ = layout(
        cursor, desc.relation, desc.field, description)
    raw_id = cursor._stmt._out_buffer[desc.offset:desc.offset + desc.length]
    array_id = api.ISC_QUAD.from_buffer_copy(raw_id)
    if code == 14:
        from .varying_arrays import read_fixed
        return True, read_fixed(cursor, array_id, bounds, dimensions,
                                characters, charset)
    if code == 37 and charset == 1:
        from .varying_arrays import read as read_varying
        return True, read_varying(cursor, array_id, bounds, dimensions)
    if code == 37 and charset in TEXT_CHARSETS:
        from .varying_arrays import read_text
        return True, read_text(cursor, array_id, bounds, dimensions,
                               characters, charset)
    raise RelationalClientError(
        'Variable ARRAY character set requires a lossless slice adapter')


def encode(values, dimensions, description, encoding):
    """Validate every element before allocating a native array slice."""
    code, characters, charset, width = description
    if code == 37 and charset not in (1, *TEXT_CHARSETS):
        raise RelationalClientError(
            'Variable ARRAY character set requires a lossless slice adapter')
    capacity = characters * width
    size = capacity + (2 if code == 37 else 0)
    leaves = []

    def visit(items, depth):
        if (not isinstance(items, (list, tuple)) or
                len(items) != dimensions[depth]):
            raise RelationalClientError('Character array dimension mismatch')
        for item in items:
            if depth < len(dimensions)-1:
                visit(item, depth + 1)
                continue
            if charset == 1:
                from .grid_values import bind_value
                item = bind_value(item)
                if (not isinstance(item, (bytes, bytearray)) or
                        len(item) > capacity):
                    raise RelationalClientError(
                        'OCTETS array requires bytes within declared length')
                leaves.append(bytes(item) if code == 37 else
                              bytes(item).ljust(size, b'\0'))
                continue
            if not isinstance(item, str) or len(item) > characters:
                raise RelationalClientError(
                    'Character array element exceeds declared length '
                    'or is not text')
            try:
                packed = item.encode(encoding)
            except UnicodeError as exc:
                raise RelationalClientError(
                    'Character array cannot use attachment encoding') from exc
            if len(packed) > capacity or (
                    code == 37 and charset not in TEXT_CHARSETS and
                    b'\0' in packed):
                raise RelationalClientError(
                    'Character array exceeds slice capacity or contains '
                    'NUL in a VARCHAR slice')
            if code == 37 and charset in TEXT_CHARSETS:
                leaves.append(packed)
            else:
                padding = b'\0' if code == 37 else b' '
                leaves.append(packed.ljust(size, padding))

    visit(values, 0)
    return (leaves if code == 37 and charset in (1, *TEXT_CHARSETS)
            else b''.join(leaves))


def pack(cursor, meta, buffer, parameters, native_pack):
    """Bind character arrays with attachment-sized native slice descriptors."""
    if len(parameters) != meta.get_count():
        return native_pack(meta, buffer, parameters)
    delegated = list(parameters)
    pending = []
    for index, value in enumerate(parameters):
        if value is None or meta.get_type(index) != SQLDataType.ARRAY:
            continue
        relation, field = meta.get_relation(index), meta.get_field(index)
        description = metadata(cursor, relation, field)
        if description is None:
            continue
        bounds, dimensions, _, _ = layout(cursor, relation, field, description)
        data = encode(value, dimensions, description, cursor._encoding)
        pending.append((index, bounds, data, description[2], description[0]))
        delegated[index] = None
    result_meta, result_buffer = native_pack(meta, buffer, delegated)
    try:
        for index, bounds, data, charset, code in pending:
            array_id = api.ISC_QUAD(0, 0)
            if code == 37 and charset in (1, *TEXT_CHARSETS):
                from .varying_arrays import write as write_varying
                write_varying(cursor, array_id, bounds, data,
                              charset=(1 if charset == 1 else
                                       transport_charset(cursor)))
            elif charset == 1:
                packed = create_string_buffer(data, len(data))
                from .array_sdl import octets
                cursor._connection._att.put_slice(
                    cursor._transaction._tra, array_id, octets(bounds), b'',
                    packed)
            else:
                packed = create_string_buffer(data, len(data))
                from .array_sdl import text_slice
                cursor._connection._att.put_slice(
                    cursor._transaction._tra, array_id,
                    text_slice(bounds, transport_charset(cursor)), b'', packed)
            if result_meta.get_length(index) != 8:
                raise RelationalClientError('Invalid native array identifier')
            memmove(addressof(result_buffer) + result_meta.get_offset(index),
                    addressof(array_id), 8)
            result_buffer[result_meta.get_null_offset(index)] = b'\0'
    except BaseException:
        # native_pack transfers one metadata reference to its caller.
        result_meta.release()
        raise
    return result_meta, result_buffer


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
            if getattr(cursor, 'stream_arrays', False):
                from .array_stream import ArrayReader
                handled, value = True, ArrayReader(cursor, desc)
            else:
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
    for index, desc in enumerate(cursor._stmt._out_desc):
        if (desc.datatype == SQLDataType.TEXT and result[index] is not None
                and TEXT_CHARSETS.get(getattr(desc, 'charset', None),
                                      (None, 1))[1] == 2):
            # The qualified driver only removes transport expansion for
            # UTF8/FSS/GB18030. Other multibyte CHAR buffers need it too.
            value, capacity = result[index], desc.length // 2
            if (desc.length % 2 or not isinstance(value, str) or
                    len(value) < capacity or value[capacity:].strip(' ')):
                raise RelationalClientError('Fixed character padding invalid')
            result[index] = value[:capacity]
    return tuple(result)
