"""Catalog ARRAY coordinates and public SDL without legacy narrowing."""
from types import SimpleNamespace

from pgadmin.cdeadmin.sdk.relational import RelationalClientError


SCALAR_WIDTHS = {7: 2, 8: 4, 16: 8, 26: 16, 10: 4, 27: 8, 23: 1,
                 24: 8, 25: 16, 12: 4, 13: 4, 35: 8, 28: 8, 29: 12}


def lookup(cursor, relation, field):
    with cursor._transaction.cursor() as catalog:
        catalog.execute(
            'SELECT F.RDB$FIELD_TYPE, F.RDB$FIELD_SUB_TYPE, '
            'F.RDB$FIELD_SCALE, F.RDB$FIELD_LENGTH, D.RDB$DIMENSION, '
            'D.RDB$LOWER_BOUND, D.RDB$UPPER_BOUND '
            'FROM RDB$RELATION_FIELDS R JOIN RDB$FIELDS F ON '
            'F.RDB$FIELD_NAME=R.RDB$FIELD_SOURCE JOIN RDB$FIELD_DIMENSIONS D '
            'ON D.RDB$FIELD_NAME=F.RDB$FIELD_NAME '
            'WHERE R.RDB$RELATION_NAME=? AND R.RDB$FIELD_NAME=? '
            'ORDER BY D.RDB$DIMENSION', (relation, field))
        rows = catalog.fetchall()
    if (not 1 <= len(rows) <= 16 or
            [row[4] for row in rows] != list(range(len(rows)))):
        raise RelationalClientError('Native ARRAY dimensions unavailable')
    bounds = []
    for row in rows:
        low, high = row[5:7]
        if (type(low) is not int or type(high) is not int or
                not -(2**31) <= low <= high < 2**31):
            raise RelationalClientError('Invalid native ARRAY coordinates')
        bounds.append(SimpleNamespace(array_bound_lower=low,
                                      array_bound_upper=high))
    count = 1
    for bound in bounds:
        count *= bound.array_bound_upper - bound.array_bound_lower + 1
    width = rows[0][3] + (2 if rows[0][0] == 37 else 0)
    if width < 1 or count * width > 2147483647:
        raise RelationalClientError('ARRAY exceeds native stored size')
    result = SimpleNamespace(
        array_desc_dtype=rows[0][0], array_desc_scale=rows[0][2] or 0,
        array_desc_length=rows[0][3], array_desc_dimensions=len(rows),
        array_desc_relation_name=relation.encode('utf8'),
        array_desc_field_name=field.encode('utf8'),
        array_desc_bounds=bounds, stored_element_width=width)
    return result, rows[0][1] or 0


def scalar_sdl(bounds):
    code = bounds.array_desc_dtype
    if (code not in SCALAR_WIDTHS or
            bounds.array_desc_length != SCALAR_WIDTHS[code] or
            not -128 <= bounds.array_desc_scale <= 127 or
            not 1 <= bounds.array_desc_dimensions <= 16):
        raise RelationalClientError('Invalid native scalar ARRAY layout')
    descriptor = bytes([code])
    if code in (7, 8, 16, 26):
        descriptor += bytes([bounds.array_desc_scale & 255])
    return program(bounds, descriptor)


def program(bounds, descriptor):
    # Relative loop counters avoid incrementing INT32_MAX after the final
    # element. Scalar expressions add the original lower coordinate back.
    count = bounds.array_desc_dimensions
    if (not 1 <= count <= 16 or len(bounds.array_desc_bounds) < count):
        raise RelationalClientError('Invalid native ARRAY dimensions')
    result = bytearray([1, 6, 1])
    result.extend(descriptor)
    for tag, name in ((2, bounds.array_desc_relation_name),
                      (4, bounds.array_desc_field_name)):
        if (not isinstance(name, bytes) or not 1 <= len(name) <= 255 or
                b'\0' in name):
            raise RelationalClientError('Invalid native ARRAY source name')
        result.extend([tag, len(name)])
        result.extend(name)
    for index, bound in enumerate(bounds.array_desc_bounds[:count]):
        low, high = bound.array_bound_lower, bound.array_bound_upper
        if (type(low) is not int or type(high) is not int or
                not -(2**31) <= low <= high < 2**31 or
                high-low >= 2**31-1):
            raise RelationalClientError('Invalid native ARRAY coordinates')
        result.extend([34, index, 11])
        result.extend(bytes(4))
        result.append(11)
        result.extend((high-low).to_bytes(4, 'little', signed=True))
    result.extend([36, 1, 8, 0, count])
    for index, bound in enumerate(bounds.array_desc_bounds[:count]):
        result.extend([13, 11])  # add(long_integer(lower), variable(index))
        result.extend(bound.array_bound_lower.to_bytes(
            4, 'little', signed=True))
        result.extend([7, index])
    result.append(255)
    return bytes(result)
