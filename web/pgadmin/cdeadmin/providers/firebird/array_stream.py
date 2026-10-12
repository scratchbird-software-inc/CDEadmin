"""Transaction-bound array references with bounded, coordinate-aware pulls."""
from copy import deepcopy
import math

from firebird.driver import fbapi

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from . import character_arrays, scalar_arrays, varying_arrays
from .query_values import normalize_value

SLICE_BYTES = 65536
SLICE_ELEMENTS = 256


class ArrayReader:
    def __init__(self, cursor, desc):
        self.cursor = cursor
        self.closed = False
        self.characters = character_arrays.metadata(
            cursor, desc.relation, desc.field)
        if self.characters is not None:
            bounds, _, width, _ = character_arrays.layout(
                cursor, desc.relation, desc.field, self.characters)
            code, chars, charset, _ = self.characters
            if code == 37 and charset != 1:
                if charset not in varying_arrays.TEXT_CHARSETS:
                    raise RelationalClientError(
                        'ARRAY streaming charset is not qualified')
                width = max(width, chars *
                            varying_arrays.TEXT_CHARSETS[charset][1])
            self.subtype = 0
        else:
            layout = scalar_arrays.describe(cursor, desc)
            if layout is None:
                raise RelationalClientError(
                    'ARRAY streaming element type is not qualified')
            bounds, width, self.subtype = layout
        self.bounds = bounds
        self.width = width
        self.dimensions = [bound.array_bound_upper -
                           bound.array_bound_lower + 1 for bound in
                           bounds.array_desc_bounds[
                               :bounds.array_desc_dimensions]]
        if (not 1 <= len(self.dimensions) <= 16 or
                any(size <= 0 for size in self.dimensions) or
                not 1 <= width <= SLICE_BYTES):
            raise RelationalClientError('Invalid streamed ARRAY bounds')
        self.count = math.prod(self.dimensions)
        stored_width = getattr(bounds, 'stored_element_width', width)
        if self.count * stored_width > 2147483647:
            raise RelationalClientError('ARRAY exceeds native slice size')
        # The cursor row buffer is reused by the next fetch. Copy identity now.
        self.array_id = fbapi.ISC_QUAD.from_buffer_copy(
            cursor._stmt._out_buffer[desc.offset:desc.offset + desc.length])

    def describe(self):
        return {'bounds': [[b.array_bound_lower, b.array_bound_upper]
                           for b in self.bounds.array_desc_bounds[
                               :self.bounds.array_desc_dimensions]],
                'element_count': self.count,
                'native_element_type': self.bounds.array_desc_dtype,
                'scale': self.bounds.array_desc_scale,
                'subtype': self.subtype,
                'charset_id': (self.characters[2]
                               if self.characters is not None else None)}

    def close(self):
        self.closed = True
        self.cursor = None

    def read(self, offset):
        if (self.closed or type(offset) is not int or
                not 0 <= offset < self.count):
            raise RelationalClientError('Invalid ARRAY element offset')
        remainder = offset
        coordinates = [0] * len(self.dimensions)
        for index in range(len(self.dimensions) - 1, -1, -1):
            remainder, position = divmod(remainder, self.dimensions[index])
            coordinates[index] = (position + self.bounds.array_desc_bounds[
                index].array_bound_lower)
        remaining = (self.bounds.array_desc_bounds[
            len(coordinates) - 1].array_bound_upper - coordinates[-1] + 1)
        count = min(remaining, SLICE_ELEMENTS, SLICE_BYTES // self.width)
        part = deepcopy(self.bounds)
        for index, coordinate in enumerate(coordinates):
            part.array_desc_bounds[index].array_bound_lower = coordinate
            part.array_desc_bounds[index].array_bound_upper = coordinate
        part.array_desc_bounds[len(coordinates) - 1].array_bound_upper += (
            count - 1)
        shape = [1] * (len(coordinates) - 1) + [count]
        if self.characters is None:
            values = scalar_arrays.rectangle(
                self.cursor, self.array_id, part, self.width, self.subtype,
                shape)
        else:
            code, characters, charset, _ = self.characters
            if code == 14:
                values = varying_arrays.read_fixed(
                    self.cursor, self.array_id, part, shape, characters,
                    charset)
            elif charset == 1:
                values = varying_arrays.read(
                    self.cursor, self.array_id, part, shape)
            else:
                values = varying_arrays.read_text(
                    self.cursor, self.array_id, part, shape, characters,
                    charset)
        for _ in range(len(coordinates) - 1):
            values = values[0]
        return {'offset': offset, 'next_offset': offset + count,
                'coordinates': coordinates,
                'values': [normalize_value(value) for value in values],
                'complete': offset + count == self.count}
