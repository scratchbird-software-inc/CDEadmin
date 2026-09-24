"""Variable binary/text slices without C-string truncation."""
from ctypes import create_string_buffer
from itertools import product

from firebird.driver import fbapi
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .array_sdl import text_slice

# Firebird intl/charsets.h identifiers; other charsets require qualification.
TEXT_CHARSETS = {2: ('ascii', 1), 4: ('utf8', 4),
                 21: ('iso8859_1', 1), 53: ('cp1252', 1)}


def read_text(cursor, array_id, bounds, dimensions, characters, charset):
    """Recover character lengths raw; let Firebird perform transliteration."""
    encoding, width = TEXT_CHARSETS[charset]
    if not 1 <= characters * width <= 65535:
        raise RelationalClientError(
            'Stored character slice width out of range')
    stored = fbapi.ISC_ARRAY_DESC.from_buffer_copy(bounds)
    stored.array_desc_length = characters * width
    originals = read(cursor, array_id, stored, dimensions)
    count = 1
    for dimension in dimensions:
        count *= dimension
    capacity = bounds.array_desc_length
    data = create_string_buffer(count * capacity)
    received = cursor._connection._att.get_slice(
        cursor._transaction._tra, array_id, text_slice(bounds, 127), b'', data)
    if received != len(data):
        raise RelationalClientError('Incomplete variable text array slice')
    raw = data.raw
    position = 0

    def decode(items, depth):
        nonlocal position
        result = []
        for item in items:
            if depth < len(dimensions) - 1:
                result.append(decode(item, depth + 1))
                continue
            length = len(item.decode(encoding))
            value = raw[position:position+capacity].decode(cursor._encoding)
            position += capacity
            if len(value) < length or value[length:].strip(' '):
                raise RelationalClientError('Variable text padding invalid')
            result.append(value[:length])
        return result

    return decode(originals, 0)


def unpad(zero, space):
    """Recover data length from two native, differently padded raw copies."""
    if len(zero) != len(space):
        raise RelationalClientError('Variable slice lengths disagree')
    end = next((i for i, pair in enumerate(zip(zero, space))
                if pair[0] != pair[1]), len(zero))
    if zero[end:] != b'\0' * (len(zero)-end) or space[end:] != (
            b' ' * (len(space)-end)):
        raise RelationalClientError('Variable slice padding disagrees')
    return zero[:end]


def read(cursor, array_id, bounds, dimensions):
    count = 1
    for dimension in dimensions:
        count *= dimension
    width = bounds.array_desc_length
    buffers = []
    for charset in (1, 0):  # OCTETS zero-pads; NONE space-pads raw bytes.
        data = create_string_buffer(count * width)
        received = cursor._connection._att.get_slice(
            cursor._transaction._tra, array_id, text_slice(bounds, charset),
            b'', data)
        if received != len(data):
            raise RelationalClientError('Incomplete variable array slice')
        buffers.append(data.raw)
    values = iter(unpad(buffers[0][i:i+width], buffers[1][i:i+width])
                  for i in range(0, count * width, width))

    def nest(depth):
        return [next(values) if depth == len(dimensions)-1 else nest(depth+1)
                for _ in range(dimensions[depth])]

    return nest(0)


def write(cursor, array_id, bounds, values, *, charset=1):
    ranges = [range(bound.array_bound_lower, bound.array_bound_upper + 1)
              for bound in bounds.array_desc_bounds[
                  :bounds.array_desc_dimensions]]
    count = 1
    for extent in ranges:
        count *= len(extent)
    if len(values) != count:
        raise RelationalClientError('Variable array element count mismatch')
    for coordinates, value in zip(product(*ranges), values):
        leaf = fbapi.ISC_ARRAY_DESC.from_buffer_copy(bounds)
        for index, coordinate in enumerate(coordinates):
            leaf.array_desc_bounds[index].array_bound_lower = coordinate
            leaf.array_desc_bounds[index].array_bound_upper = coordinate
        # A length-sized text descriptor preserves NULs and trailing bytes.
        # Empty values use a one-byte empty C string; SDL disallows width zero.
        leaf.array_desc_length = len(value) or 1
        data = create_string_buffer(value or b'\0', len(value) or 1)
        cursor._connection._att.put_slice(
            cursor._transaction._tra, array_id,
            text_slice(leaf, charset, cstring=not value), b'', data)
