"""Bounded character slices and lossless variable binary/text transport."""
from copy import deepcopy
from ctypes import create_string_buffer
from itertools import chain, product

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .array_sdl import text_slice, transport_charset
from .attachment_codecs import PRIVATE_CHARSETS, codec_name, native_name

# Firebird intl/charsets.h identifiers; other charsets require qualification.
TEXT_CHARSETS = {
    # Single-byte encodings need byte counts, not Python transliteration.
    # Firebird converts the separate dynamic-charset slice itself.
    **{identifier: ('latin1', 1) for identifier in (
        *range(9, 20), 21, 22, 23, *range(34, 41), *range(45, 56),
        58, 59, 60, 63, 64, 65, 66)},
    0: (None, 1), 2: ('ascii', 1), 3: ('utf8', 3), 4: ('utf8', 4),
    5: ('shift_jis', 2), 6: ('euc_jp', 2), 44: ('euc_kr', 2),
    56: ('big5', 2), 57: ('gb2312', 2), 67: ('gbk', 2),
    68: ('cp932', 2), 69: ('gb18030', 4),
}
SLICE_BYTES = 1024 * 1024


def chunks(bounds, dimensions, width):
    """Yield contiguous row-major rectangles with bounded native buffers."""
    if (not 1 <= len(dimensions) <= 16 or
            len(dimensions) != bounds.array_desc_dimensions or
            not 1 <= width <= 65535):
        raise RelationalClientError('Invalid variable array slice metadata')
    count = 1
    for index, size in enumerate(dimensions):
        bound = bounds.array_desc_bounds[index]
        if size <= 0 or size != (
                bound.array_bound_upper - bound.array_bound_lower + 1):
            raise RelationalClientError('Variable array bounds disagree')
        count *= size
    if count * width <= SLICE_BYTES:
        yield bounds, dimensions
        return
    index = next((i for i, size in enumerate(dimensions) if size > 1), None)
    if index is None:
        raise RelationalClientError(
            'Variable array element exceeds buffer cap')
    size = dimensions[index]
    lower = bounds.array_desc_bounds[index].array_bound_lower
    left = size // 2
    for start, length in ((lower, left), (lower + left, size - left)):
        part = deepcopy(bounds)
        part.array_desc_bounds[index].array_bound_lower = start
        part.array_desc_bounds[index].array_bound_upper = start + length - 1
        shape = list(dimensions)
        shape[index] = length
        yield from chunks(part, shape, width)


def _chunked(bounds, dimensions, width, reader):
    parts = iter(chunks(bounds, dimensions, width))
    first = next(parts)  # Validate all original bounds before reconstruction.
    if first[0] is bounds:
        return reader(*first)

    def flatten(items, depth):
        for item in items:
            if depth == len(dimensions) - 1:
                yield item
            else:
                yield from flatten(item, depth + 1)

    def values():
        for part, shape in chain((first,), parts):
            yield from flatten(reader(part, shape), 0)

    leaves = values()

    def nest(depth):
        return [next(leaves) if depth == len(dimensions) - 1 else nest(depth+1)
                for _ in range(dimensions[depth])]

    return nest(0)


def read_text(cursor, array_id, bounds, dimensions, characters, charset):
    """Recover character lengths raw; let Firebird perform transliteration."""
    encoding, width = TEXT_CHARSETS[charset]
    if not 1 <= characters * width <= 65535:
        raise RelationalClientError(
            'Stored character slice width out of range')
    return _chunked(
        bounds, dimensions, max(characters * width, bounds.array_desc_length),
        lambda part, shape: _read_text(
            cursor, array_id, part, shape, characters, charset))


def read_fixed(cursor, array_id, bounds, dimensions, characters, charset):
    """Preserve fixed-width bytes or characters using bounded native slices."""
    if charset == 0:
        stored = deepcopy(bounds)
        stored.array_desc_length = characters
        return _decode_nested(read_fixed(
            cursor, array_id, stored, dimensions, characters, 1),
            cursor._encoding)

    def rectangle(part, shape):
        count = 1
        for size in shape:
            count *= size
        capacity = part.array_desc_length
        data = create_string_buffer(count * capacity)
        selected = 1 if charset == 1 else transport_charset(cursor)
        received = cursor._connection._att.get_slice(
            cursor._transaction._tra, array_id,
            text_slice(part, selected), b'', data)
        if received != len(data):
            raise RelationalClientError('Incomplete fixed array slice')
        raw = data.raw

        def values():
            for offset in range(0, len(raw), capacity):
                value = raw[offset:offset+capacity]
                if charset != 1:
                    value = value.decode(cursor._encoding)
                    if (len(value) < characters or
                            value[characters:].strip(' ')):
                        raise RelationalClientError(
                            'Character array padding invalid')
                    value = value[:characters]
                yield value

        leaves = values()

        def nest(depth):
            return [next(leaves) if depth == len(shape)-1 else nest(depth+1)
                    for _ in range(shape[depth])]

        return nest(0)

    return _chunked(bounds, dimensions, bounds.array_desc_length, rectangle)


def _decode_nested(values, encoding):
    return [_decode_nested(value, encoding) if isinstance(value, list) else
            value.decode(encoding) for value in values]


def _text_length(raw, charset, connection=None):
    name = native_name(charset)
    encoding = (codec_name(name) if name in PRIVATE_CHARSETS
                else TEXT_CHARSETS[charset][0])
    if name == 'GB18030' and connection is not None:
        from .gb18030_profile import encoding as native_encoding
        encoding = native_encoding(connection)
    return len(raw.decode(encoding))


def _read_text(cursor, array_id, bounds, dimensions, characters, charset):
    _, width = TEXT_CHARSETS[charset]
    stored = deepcopy(bounds)
    stored.array_desc_length = characters * width
    originals = _read(cursor, array_id, stored, dimensions)
    if charset == 0:
        return _decode_nested(originals, cursor._encoding)
    count = 1
    for dimension in dimensions:
        count *= dimension
    capacity = bounds.array_desc_length
    data = create_string_buffer(count * capacity)
    received = cursor._connection._att.get_slice(
        cursor._transaction._tra, array_id,
        text_slice(bounds, transport_charset(cursor)), b'', data)
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
            length = _text_length(item, charset, cursor._connection)
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
    return _chunked(bounds, dimensions, bounds.array_desc_length,
                    lambda part, shape: _read(cursor, array_id, part, shape))


def _read(cursor, array_id, bounds, dimensions):
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
        leaf = deepcopy(bounds)
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
