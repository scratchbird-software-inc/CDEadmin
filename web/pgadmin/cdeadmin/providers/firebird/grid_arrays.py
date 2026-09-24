"""Validate array parameters against native metadata before driver packing.

The driver uses ctypes integers for array slices, which can silently wrap.
Client-provided type labels are never authoritative for these checks.
"""
from decimal import Decimal, DecimalException, localcontext
import re

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .grid_values import bind_value


def descriptor(catalog, relation, field):
    catalog.execute(
        'SELECT F.RDB$FIELD_TYPE, F.RDB$FIELD_SUB_TYPE, '
        'F.RDB$FIELD_SCALE, D.RDB$DIMENSION, '
        'D.RDB$LOWER_BOUND, D.RDB$UPPER_BOUND '
        'FROM RDB$RELATION_FIELDS R JOIN RDB$FIELDS F ON '
        'F.RDB$FIELD_NAME = R.RDB$FIELD_SOURCE '
        'JOIN RDB$FIELD_DIMENSIONS D ON '
        'D.RDB$FIELD_NAME = F.RDB$FIELD_NAME '
        'WHERE R.RDB$RELATION_NAME = ? AND R.RDB$FIELD_NAME = ? '
        'ORDER BY D.RDB$DIMENSION', (relation, field))
    rows = catalog.fetchall()
    if not rows or [row[3] for row in rows] != list(range(len(rows))):
        raise RelationalClientError(
            'Firebird array destination metadata unavailable')
    return {'type': rows[0][0], 'subtype': rows[0][1] or 0,
            'scale': rows[0][2] or 0,
            'bounds': [(row[4], row[5]) for row in rows]}


def editor_specs(connection, columns):
    result = {}
    for column in columns:
        if column.get('native_type') != 'ARRAY' or not column.get(
                'source_relation') or not column.get('source_field'):
            continue
        with connection.cursor() as catalog:
            spec = descriptor(catalog, column['source_relation'],
                              column['source_field'])
        kind = {7: 'integer', 8: 'integer', 16: 'integer', 26: 'integer',
                10: 'float32', 27: 'float64', 23: 'boolean'}.get(spec['type'])
        if kind == 'integer' and (spec['subtype'] or spec['scale']):
            kind = 'decimal'
        if kind:
            result[column['native_name']] = {**spec, 'element_kind': kind}
    return result


def convert(value, spec):
    """Preserve native bounds and reject lossy fixed-width element input."""
    if value is None:
        return None
    bounds = spec['bounds']
    if not bounds or len(bounds) > 16:
        raise RelationalClientError('Firebird array bounds are unavailable')

    def leaf(item):
        code = spec['type']
        if code in (7, 8, 16, 26):
            bits = {7: 16, 8: 32, 16: 64, 26: 128}[code]
            fixed = bool(spec['subtype'] or spec['scale'])
            if type(item) not in (str, int, Decimal):
                raise RelationalClientError(
                    'Firebird array exact numbers require integer or text '
                    'input, not floating-point JSON numbers')
            text = str(item)
            pattern = (r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
                       if fixed else r'[+-]?\d+')
            if not re.fullmatch(pattern, text, re.ASCII):
                raise RelationalClientError('Invalid Firebird array number')
            try:
                number = Decimal(text)
                with localcontext() as context:
                    context.prec = max(50, len(number.as_tuple().digits) + 2)
                    scaled = number.scaleb(-spec['scale'])
                    if (scaled != scaled.to_integral_value() or
                            scaled < -(1 << (bits - 1)) or
                            scaled > (1 << (bits - 1)) - 1):
                        raise RelationalClientError(
                            'Firebird array number exceeds native range '
                            'or scale')
                return number if fixed else int(number)
            except (DecimalException, OverflowError):
                raise RelationalClientError('Invalid Firebird array number')
        if code in (10, 27):
            if type(item) not in (str, int, float):
                raise RelationalClientError('Invalid Firebird array float')
            return bind_value({'encoding': 'float32' if code == 10 else
                               'float64', 'data': str(item)})
        if code == 23:
            if type(item) is not bool:
                raise RelationalClientError('Firebird array requires Boolean')
            return item
        if item is None:
            raise RelationalClientError(
                'Firebird array elements cannot be NULL')
        # Other element types retain native driver validation; no conversion
        # is advertised here without a verified lossless native binding.
        return item

    def dimension(items, depth):
        lower, upper = bounds[depth]
        if not isinstance(items, (list, tuple)) or len(items) != upper-lower+1:
            raise RelationalClientError(
                f'Firebird array dimension {depth + 1} requires bounds '
                f'{lower}:{upper} ({upper-lower+1} elements)')
        return [leaf(item) if depth == len(bounds)-1 else
                dimension(item, depth+1) for item in items]

    return dimension(value, 0)


def parameters(connection, cursor, source, values):
    """Resolve array destinations from the exact prepared DML, not the UI."""
    if not any(isinstance(value, (list, tuple)) for value in values):
        return values
    statement = cursor.prepare(source)
    try:
        from firebird.driver.types import SQLDataType
        meta = statement._in_meta
        if meta is None or meta.get_count() != len(values):
            raise RelationalClientError('Firebird array metadata unavailable')
        result = list(values)
        with connection.cursor() as catalog:
            for index, value in enumerate(values):
                if meta.get_type(index) != SQLDataType.ARRAY:
                    continue
                result[index] = convert(value, descriptor(
                    catalog, meta.get_relation(index), meta.get_field(index)))
        return tuple(result)
    finally:
        statement.free()
