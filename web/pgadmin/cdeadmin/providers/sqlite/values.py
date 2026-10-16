"""SQLite storage values and native bindings at the browser boundary."""
import base64
import datetime
import math
from collections.abc import Mapping
from decimal import Decimal

from pgadmin.cdeadmin.sdk import RelationalClientError

SAFE_INTEGER = (1 << 53) - 1


class NativeTextBytes(bytes):
    """TEXT bytes which have no lossless Unicode representation."""


def text(raw):
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        return NativeTextBytes(raw)


def value(item):
    if item is None or isinstance(item, (str, bool)):
        return item
    if isinstance(item, int):
        return item if abs(item) <= SAFE_INTEGER else str(item)
    if isinstance(item, float):
        return repr(item)
    if isinstance(item, (bytes, bytearray, memoryview)):
        result = {'encoding': 'base64',
                  'data': base64.b64encode(item).decode('ascii'),
                  'byte_length': len(item)}
        if isinstance(item, NativeTextBytes):
            result['native_storage_class'] = 'text'
        return result
    if isinstance(item, (datetime.date, datetime.time, Decimal)):
        # Explicit detect_types/custom converter outputs are separate from
        # SQLite's native storage classes. Never narrow them further.
        return str(item)
    raise RelationalClientError(
        'SQLite converter returned an unsupported value')


def parameter(item):
    if item is None or isinstance(item, (str, bool, bytes)):
        return item
    if type(item) is int and abs(item) <= SAFE_INTEGER:
        return item
    if type(item) is float and math.isfinite(item):
        return item
    if isinstance(item, Mapping):
        kind, data = item.get('encoding'), item.get('data')
        if not isinstance(data, str):
            raise RelationalClientError('SQLite exact parameter needs text')
        if kind == 'integer' and set(item) == {'encoding', 'data'}:
            try:
                number = int(data)
                if str(number) == data and -(1 << 63) <= number < (1 << 63):
                    return number
            except ValueError:
                pass
        if kind == 'base64' and not set(item).difference({
                'encoding', 'data', 'byte_length'}):
            try:
                result = base64.b64decode(data, validate=True)
            except ValueError:
                raise RelationalClientError(
                    'SQLite binary binding is invalid') from None
            if 'byte_length' not in item or (
                    type(item['byte_length']) is int and
                    item['byte_length'] == len(result)):
                return result
    raise RelationalClientError(
        'SQLite parameter requires a native value or exact envelope')


def archive_value(item):
    """Preserve SQLite's dynamic storage class, including numeric TEXT."""
    if type(item) is int and abs(item) > SAFE_INTEGER:
        return {'encoding': 'integer', 'data': str(item)}
    if type(item) is float:
        return {'encoding': 'float64', 'data': repr(item)}
    return value(item)


def parameters(items):
    if items is None:
        return ()
    if isinstance(items, Mapping):
        if not all(isinstance(key, str) for key in items):
            raise RelationalClientError('SQLite binding names must be text')
        return {key: parameter(item) for key, item in items.items()}
    if isinstance(items, (list, tuple)):
        return tuple(parameter(item) for item in items)
    raise RelationalClientError('SQLite parameters must be an object or array')
