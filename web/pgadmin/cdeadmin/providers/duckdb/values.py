"""Exact DuckDB Arrow presentation and native parameter envelopes."""
import base64
import decimal
import math
import re
import sys
import uuid

from pgadmin.cdeadmin.sdk import RelationalClientError

SAFE_INTEGER = 2**53 - 1


def binary(data):
    return {'encoding': 'base64',
            'data': base64.b64encode(data).decode('ascii'),
            'byte_length': len(data)}


def scalar(item):
    import pyarrow as pa
    if not item.is_valid:
        return None
    kind = item.type
    if isinstance(kind, pa.BaseExtensionType):
        if kind.extension_name == 'arrow.uuid':
            return str(item.as_py())
        stored = item.value
        name = getattr(kind, 'type_name', kind.extension_name)
        if name in {'hugeint', 'uhugeint'}:
            return str(int.from_bytes(stored.as_py(), sys.byteorder,
                                      signed=name == 'hugeint'))
        return {'encoding': 'duckdb-arrow-opaque', 'native_type': name,
                'vendor': getattr(kind, 'vendor_name', None),
                'storage_type': str(kind.storage_type),
                'storage': scalar(stored)}
    if pa.types.is_dictionary(kind):
        return scalar(item.value)
    if pa.types.is_union(kind):
        tag = kind.type_codes.index(item.type_code)
        return {'tag': kind[tag].name, 'type_code': item.type_code,
                'value': scalar(item.value)}
    if pa.types.is_struct(kind):
        return {field.name: scalar(item[field.name]) for field in kind}
    if pa.types.is_map(kind):
        return {'encoding': 'map', 'entries': [
            [scalar(pair['key']), scalar(pair['value'])]
            for pair in item.values]}
    if (pa.types.is_list(kind) or pa.types.is_large_list(kind) or
            pa.types.is_fixed_size_list(kind) or pa.types.is_list_view(kind) or
            pa.types.is_large_list_view(kind)):
        return [scalar(child) for child in item.values]
    if pa.types.is_interval(kind):
        interval = item.as_py()
        return {'months': interval.months, 'days': interval.days,
                'nanoseconds': str(interval.nanoseconds)}
    if pa.types.is_temporal(kind):
        return {'encoding': 'temporal-ticks', 'arrow_type': str(kind),
                'ticks': str(item.value)}
    value = item.as_py()
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return str(value) if abs(value) > SAFE_INTEGER else value
    if isinstance(value, (float, decimal.Decimal)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return binary(bytes(value))
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str) or value is None:
        return value
    raise RelationalClientError('DuckDB Arrow value is not representable')


def parameter(value):
    import duckdb
    if isinstance(value, dict):
        encoding = value.get('encoding')
        if encoding in {'integer', 'decimal', 'base64'}:
            if set(value) - {'encoding', 'data', 'byte_length'}:
                raise RelationalClientError('DuckDB parameter fields invalid')
            data = value.get('data')
            if not isinstance(data, str):
                raise RelationalClientError(
                    'DuckDB exact parameter needs text')
            if encoding == 'base64':
                try:
                    result = base64.b64decode(data, validate=True)
                except Exception:
                    raise RelationalClientError(
                        'DuckDB binary parameter is invalid') from None
                if ('byte_length' in value and
                        value['byte_length'] != len(result)):
                    raise RelationalClientError('DuckDB binary length differs')
                return result
            if encoding == 'integer':
                if not re.fullmatch(r'-?(0|[1-9][0-9]*)', data):
                    raise RelationalClientError('DuckDB integer is invalid')
                integer = int(data)
                if -(2**127) <= integer < 2**127:
                    kind = 'HUGEINT'
                elif 0 <= integer < 2**128:
                    kind = 'UHUGEINT'
                else:
                    kind = 'BIGNUM'
                return duckdb.Value(data, duckdb.sqltype(kind))
            if not re.fullmatch(r'-?(0|[1-9][0-9]*)(\.[0-9]+)?', data):
                raise RelationalClientError('DuckDB decimal is invalid')
            digits = data.lstrip('-').split('.')
            scale = len(digits[1]) if len(digits) > 1 else 0
            precision = max(1, len(digits[0].lstrip('0')) + scale)
            if precision > 38 or scale > 38:
                raise RelationalClientError('DuckDB decimal exceeds precision')
            return duckdb.Value(data, duckdb.sqltype(
                f'DECIMAL({precision},{scale})'))
        if not all(isinstance(key, str) for key in value):
            raise RelationalClientError('DuckDB struct keys must be text')
        return {key: parameter(child) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [parameter(child) for child in value]
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int) and abs(value) <= SAFE_INTEGER:
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    raise RelationalClientError('DuckDB parameter needs an exact envelope')


def parameters(value):
    if value is None:
        return []
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise RelationalClientError('DuckDB parameter names must be text')
        return {key: parameter(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [parameter(child) for child in value]
    raise RelationalClientError('DuckDB parameters must be an object or array')
