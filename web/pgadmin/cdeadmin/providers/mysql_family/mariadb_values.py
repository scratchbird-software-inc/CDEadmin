"""Exact browser values from the native MariaDB connector."""
import base64
import binascii
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import math
import re
from pgadmin.cdeadmin.sdk import RelationalClientError

SAFE_INTEGER = (1 << 53) - 1


class ExactTemporalConnectorRequired(RelationalClientError):
    """No SQL is executed when the required native extension is absent."""


def value(item):
    if item is None or isinstance(item, (str, bool)):
        return item
    if isinstance(item, int):
        return item if abs(item) <= SAFE_INTEGER else str(item)
    if isinstance(item, Decimal):
        return str(item)
    if isinstance(item, float):
        if not math.isfinite(item):
            raise RelationalClientError('MariaDB nonfinite result is invalid')
        return repr(item)
    if isinstance(item, (bytes, bytearray)):
        return {'encoding': 'base64',
                'data': base64.b64encode(item).decode('ascii'),
                'byte_length': len(item)}
    raise RelationalClientError(
        'MariaDB result requires exact native decoding')


def columns(cursor):
    descriptions = cursor.description or ()
    metadata = cursor.metadata or {}
    bases = [str(item[0]) or f'column_{i + 1}'
             for i, item in enumerate(descriptions)]
    reserved, used, result = set(bases), set(), []
    for i, item in enumerate(descriptions):
        name, suffix = bases[i], 2
        while name in used:
            name = f'{bases[i]}#{suffix}'
            suffix += 1
            if name in reserved:
                name = bases[i]
        used.add(name)
        native = {key: values[i] for key, values in metadata.items()}
        # Connector/Python 1.1.14 reverses these two MYSQL_FIELD members in
        # Cursor.metadata. Keep the public metadata names semantically correct.
        if 'length' in native and 'max_length' in native:
            native['length'], native['max_length'] = (
                native['max_length'], native['length'])
        flags = native.get('flags')
        result.append({
            'name': name, 'native_name': str(item[0]), 'ordinal': i,
            'native_type': str(item[1]), 'native_type_code': item[1],
            'nullable': item[6] if len(item) > 6 else None,
            'unsigned': bool(flags & 32) if flags is not None else None,
            'native_metadata': native,
            'cell_type': 'json' if native.get('charset') == 63 and
            item[1] in {15, 16, 249, 250, 251, 252, 253, 254, 255} else 'text',
            'metadata_source': 'mariadb-connector-python.column-definition',
        })
    return result


def parameter(item):
    if isinstance(item, bytearray):
        return bytes(item)
    if item is None or isinstance(item, (str, bool, bytes)):
        return item
    if type(item) is int and abs(item) <= SAFE_INTEGER:
        return item
    if type(item) is float and math.isfinite(item):
        return item
    if isinstance(item, Mapping):
        encoding, data = item.get('encoding'), item.get('data')
        if (set(item) - {'encoding', 'data', 'byte_length'} or
                not isinstance(data, str)):
            raise RelationalClientError('MariaDB typed parameter is invalid')
        if encoding == 'base64':
            try:
                raw = base64.b64decode(data, validate=True)
            except (ValueError, binascii.Error):
                raise RelationalClientError(
                    'MariaDB binary parameter is invalid') from None
            if 'byte_length' in item and (
                    type(item['byte_length']) is not int or
                    item['byte_length'] != len(raw)):
                raise RelationalClientError(
                    'MariaDB binary parameter length does not match')
            return raw
        if set(item) != {'encoding', 'data'}:
            raise RelationalClientError('MariaDB numeric parameter is invalid')
        if encoding == 'integer' and re.fullmatch(r'-?[0-9]{1,65}', data):
            number = int(data)
            # Connector/Python's binary integer encoder silently truncates
            # wider integers. MariaDB DECIMAL binds their exact value instead.
            return (number if -(1 << 63) <= number < (1 << 64)
                    else Decimal(data))
        if encoding == 'decimal' and len(data) <= 1024:
            try:
                number = Decimal(data)
                if number.is_finite():
                    return number
            except InvalidOperation:
                pass
    raise RelationalClientError(
        'MariaDB parameter requires an exact supported value '
        'or typed envelope')


def parameters(items):
    if items is None:
        return ()
    if isinstance(items, Mapping):
        if not all(isinstance(name, str) for name in items):
            raise RelationalClientError('MariaDB parameter names must be text')
        return {name: parameter(item) for name, item in items.items()}
    if isinstance(items, (list, tuple)):
        return tuple(parameter(item) for item in items)
    raise RelationalClientError(
        'MariaDB parameters must be an object or array')


class Cursor:
    def __init__(self, connection):
        self.native = connection.cursor(buffered=False)
        if not hasattr(self.native, 'cdeadmin_exact_temporals'):
            self.native.close()
            raise ExactTemporalConnectorRequired(
                'MariaDB requires the ScratchRobin '
                'exact-temporal connector build')
        self.native.cdeadmin_exact_temporals = True

    def __getattr__(self, name):
        return getattr(self.native, name)

    def fetchone(self):
        row = self.native.fetchone()
        return None if row is None else tuple(value(item) for item in row)
