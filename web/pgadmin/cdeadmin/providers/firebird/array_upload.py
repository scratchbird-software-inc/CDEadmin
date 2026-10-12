"""Bind ARRAY files using bounded native transaction slices."""
from copy import deepcopy
from ctypes import addressof, create_string_buffer, memmove
from types import SimpleNamespace

from firebird.driver import fbapi
from firebird.driver.types import SQLDataType

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from . import character_arrays, grid_arrays, scalar_arrays, varying_arrays
from .array_file import ArrayUpload, coordinates
from .array_sdl import text_slice, transport_charset
from .array_layout import scalar_sdl


class ArrayValues:
    """Expose an ordinary parameter as shaped, bounded row-major chunks."""

    def __init__(self, values, header):
        self.values, self.header = values, header

    def chunks(self):
        dimensions = [high - low + 1 for low, high in self.header['bounds']]
        offset = 0

        def visit(items, depth):
            nonlocal offset
            if (not isinstance(items, (list, tuple)) or
                    len(items) != dimensions[depth]):
                raise RelationalClientError(
                    'ARRAY parameter dimensions do not match native bounds')
            if depth < len(dimensions) - 1:
                for item in items:
                    yield from visit(item, depth + 1)
            else:
                for start in range(0, len(items), 256):
                    part = items[start:start + 256]
                    yield offset, part
                    offset += len(part)

        yield from visit(self.values, 0)


class ArrayWriter:
    def __init__(self, cursor, relation, field, upload):
        self.cursor = cursor
        self.characters = character_arrays.metadata(cursor, relation, field)
        if self.characters is not None:
            self.bounds, _, self.width, _ = character_arrays.layout(
                cursor, relation, field, self.characters)
            self.subtype = 0
        else:
            layout = scalar_arrays.describe(cursor, SimpleNamespace(
                relation=relation, field=field))
            if layout is None:
                raise RelationalClientError(
                    'ARRAY destination type unavailable')
            self.bounds, self.width, self.subtype = layout
        with cursor._transaction.cursor() as catalog:
            self.spec = grid_arrays.descriptor(catalog, relation, field)
        actual = {'bounds': [list(pair) for pair in self.spec['bounds']],
                  'native_element_type': self.bounds.array_desc_dtype,
                  'scale': self.bounds.array_desc_scale,
                  'subtype': self.subtype,
                  'charset_id': self.spec.get('charset_id')}
        if not isinstance(upload, ArrayUpload):
            upload = ArrayValues(upload, actual)
        self.upload = upload
        header = upload.header
        if (any(header[key] != value for key, value in actual.items()) or
                not 1 <= self.width <= 65536):
            raise RelationalClientError('ARRAY file destination mismatch')
        # Complete application validation before publishing any uploaded slice.
        for _ in self._batches():
            pass

    def _batches(self):
        for offset, values in self.upload.chunks():
            maximum = min(256, 65536 // self.width)
            for start in range(0, len(values), maximum):
                leaves = values[start:start + maximum]
                count = len(leaves)
                native = grid_arrays.convert(leaves, {
                    **self.spec, 'bounds': [(0, count - 1)]})
                part = deepcopy(self.bounds)
                point = coordinates(
                    self.upload.header['bounds'], offset + start)
                for index, coordinate in enumerate(point):
                    bound = part.array_desc_bounds[index]
                    bound.array_bound_lower = coordinate
                    bound.array_bound_upper = coordinate
                bound.array_bound_upper += count - 1
                if self.characters is not None:
                    data = character_arrays.encode(
                        native, [count], self.characters,
                        self.cursor._encoding)
                    if isinstance(data, bytes):
                        data = create_string_buffer(data, len(data))
                else:
                    data = create_string_buffer(count * self.width)
                    self.cursor._copy_list_to_db_array(
                        self.width, part.array_desc_dtype, self.subtype,
                        part.array_desc_scale, 0, [count], native, data, 0)
                yield part, data

    def write(self):
        identity = fbapi.ISC_QUAD(0, 0)
        for part, data in self._batches():
            if self.characters is not None and self.characters[0] == 37:
                varying_arrays.write(
                    self.cursor, identity, part, data,
                    charset=(1 if self.characters[2] == 1 else
                             transport_charset(self.cursor)))
            else:
                sdl = (text_slice(part, 1 if self.characters[2] == 1 else
                                  transport_charset(self.cursor))
                       if self.characters is not None else scalar_sdl(part))
                self.cursor._connection._att.put_slice(
                    self.cursor._transaction._tra, identity, sdl, b'', data)
        return identity


def pack(cursor, meta, buffer, parameters, native_pack):
    candidates = [index for index, value in enumerate(parameters)
                  if isinstance(value, (ArrayUpload, list, tuple))]
    if not candidates:
        return native_pack(meta, buffer, parameters)
    if len(parameters) != meta.get_count():
        raise RelationalClientError('ARRAY parameter count mismatch')
    delegated, writers = list(parameters), []
    for index, value in enumerate(parameters):
        if index not in candidates:
            continue
        if meta.get_type(index) != SQLDataType.ARRAY:
            if isinstance(value, ArrayUpload):
                raise RelationalClientError(
                    'ARRAY file requires an ARRAY parameter')
            continue
        writer = ArrayWriter(cursor, meta.get_relation(index),
                             meta.get_field(index), value)
        writers.append((index, writer))
        delegated[index] = None
    result_meta, result_buffer = native_pack(meta, buffer, delegated)
    try:
        for index, writer in writers:
            if result_meta.get_length(index) != 8:
                raise RelationalClientError('Invalid native ARRAY identity')
            identity = writer.write()
            memmove(addressof(result_buffer) + result_meta.get_offset(index),
                    addressof(identity), 8)
            result_buffer[result_meta.get_null_offset(index)] = b'\0'
    except BaseException:
        result_meta.release()
        raise
    return result_meta, result_buffer
