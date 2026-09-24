"""Validate array parameters against native metadata before driver packing.

The driver uses ctypes integers for array slices, which can silently wrap.
Client-provided type labels are never authoritative for these checks.
"""
from decimal import (Context, Decimal, DecimalException, Inexact,
                     InvalidOperation, Overflow, localcontext)
import re

from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from .grid_values import bind_value


def descriptor(catalog, relation, field):
    catalog.execute(
        'SELECT F.RDB$FIELD_TYPE, F.RDB$FIELD_SUB_TYPE, '
        'F.RDB$FIELD_SCALE, D.RDB$DIMENSION, '
        'D.RDB$LOWER_BOUND, D.RDB$UPPER_BOUND, '
        'F.RDB$CHARACTER_LENGTH, TRIM(C.RDB$CHARACTER_SET_NAME) '
        'FROM RDB$RELATION_FIELDS R JOIN RDB$FIELDS F ON '
        'F.RDB$FIELD_NAME = R.RDB$FIELD_SOURCE '
        'JOIN RDB$FIELD_DIMENSIONS D ON '
        'D.RDB$FIELD_NAME = F.RDB$FIELD_NAME '
        'LEFT JOIN RDB$CHARACTER_SETS C ON '
        'C.RDB$CHARACTER_SET_ID = F.RDB$CHARACTER_SET_ID '
        'WHERE R.RDB$RELATION_NAME = ? AND R.RDB$FIELD_NAME = ? '
        'ORDER BY D.RDB$DIMENSION', (relation, field))
    rows = catalog.fetchall()
    if not rows or [row[3] for row in rows] != list(range(len(rows))):
        raise RelationalClientError(
            'Firebird array destination metadata unavailable')
    result = {'type': rows[0][0], 'subtype': rows[0][1] or 0,
              'scale': rows[0][2] or 0,
              'bounds': [(row[4], row[5]) for row in rows]}
    if result['type'] in (14, 37):
        result.update(length=rows[0][6], charset=rows[0][7])
    return result


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
                10: 'float32', 27: 'float64', 23: 'boolean',
                24: 'decfloat', 25: 'decfloat', 12: 'date',
                13: 'time', 35: 'timestamp'}.get(spec['type'])
        if kind == 'integer' and (spec['subtype'] or spec['scale']):
            kind = 'decimal'
        if (spec['type'] == 14 and spec.get('length') and
                spec.get('charset') in {
                    'ASCII', 'UTF8', 'ISO8859_1', 'WIN1252', 'OCTETS'}):
            kind = 'binary' if spec['charset'] == 'OCTETS' else 'text'
        if (spec['type'] == 37 and spec.get('length') and
                spec.get('charset') == 'OCTETS'):
            kind = 'binary'
        if kind:
            result[column['native_name']] = {**spec, 'element_kind': kind}
            if kind == 'decfloat':
                result[column['native_name']]['precision'] = (
                    16 if spec['type'] == 24 else 34)
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
        if code == 14 or (code == 37 and spec.get('charset') == 'OCTETS'):
            binary = spec.get('charset') == 'OCTETS'
            item = bind_value(item) if binary else item
            if (not isinstance(item, (bytes, bytearray) if binary else str) or
                    not spec.get('length') or len(item) > spec['length']):
                raise RelationalClientError(
                    'Firebird character array requires values within '
                    'its declared character or byte length')
            return item
        if code in (12, 13, 35):
            from .temporal_arrays import parse
            return parse(item, code)
        if code in (24, 25):
            if type(item) not in (str, int, Decimal) or not re.fullmatch(
                    r'[+-]?(?:(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?'
                    r'|s?NaN|Infinity)', str(item), re.ASCII | re.IGNORECASE):
                raise RelationalClientError(
                    'Firebird DECFLOAT array requires exact numeric text')
            try:
                number = Decimal(str(item), context=Context(
                    traps=[InvalidOperation]))
                if number.is_finite():
                    # Native decimal64/decimal128 limits. Reject value-changing
                    # driver rounding before slice packing; exact subnormals
                    # and explicit native special values remain available.
                    precision, emin, emax = ((16, -383, 384) if code == 24
                                             else (34, -6143, 6144))
                    Context(prec=precision, Emin=emin, Emax=emax, clamp=1,
                            traps=[Inexact, Overflow, InvalidOperation]
                            ).create_decimal(number)
                return number
            except DecimalException:
                raise RelationalClientError(
                    'Firebird DECFLOAT array value is not exactly '
                    'representable at its native precision and range')
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
